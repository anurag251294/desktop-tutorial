# Databricks notebook source / Microsoft Fabric Notebook
# MAGIC %md
# MAGIC # 04 - Document Processing
# MAGIC **Manulife Fabric POC**
# MAGIC
# MAGIC This notebook processes unstructured documents (markdown, text files) from the
# MAGIC lakehouse Files area, chunks them for downstream retrieval-augmented generation,
# MAGIC and stores the results in a delta table.
# MAGIC
# MAGIC **Pipeline:**
# MAGIC 1. Read markdown/text files from Files/raw/unstructured/
# MAGIC 2. Extract metadata (filename, section headers, document type)
# MAGIC 3. Chunk documents using sliding window (500 tokens, 50 overlap)
# MAGIC 4. Optionally generate embeddings (Azure OpenAI pattern with mock fallback)
# MAGIC 5. Write document_chunks delta table

# COMMAND ----------

from pyspark.sql import SparkSession, DataFrame, Row
from pyspark.sql.functions import (
    col, lit, current_timestamp, monotonically_increasing_id,
    udf, explode, array, size, length
)
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, LongType,
    ArrayType, FloatType, TimestampType
)
import os
import re
import uuid
import hashlib
import traceback

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

# Source path for unstructured documents
UNSTRUCTURED_PATH = "Files/raw/unstructured"
# Supported file extensions
SUPPORTED_EXTENSIONS = [".md", ".txt", ".text", ".markdown"]
# Chunking parameters
CHUNK_SIZE = 500       # Approximate token count per chunk
CHUNK_OVERLAP = 50     # Token overlap between consecutive chunks
# Embedding dimension (placeholder)
EMBEDDING_DIM = 1536   # Matches text-embedding-ada-002
# Toggle real embeddings (set to True if Azure OpenAI is configured)
USE_REAL_EMBEDDINGS = False

print(f"Source path: {UNSTRUCTURED_PATH}")
print(f"Chunk size: {CHUNK_SIZE} tokens, Overlap: {CHUNK_OVERLAP} tokens")
print(f"Real embeddings: {USE_REAL_EMBEDDINGS}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Document Reading Functions

# COMMAND ----------

def list_document_files(base_path: str, extensions: list) -> list:
    """
    List all document files from the lakehouse Files area.
    Returns a list of dicts with file_path, file_name, file_extension.
    """
    files = []
    try:
        file_list = dbutils.fs.ls(base_path)
        for f in file_list:
            name = f.name.rstrip("/")
            ext = os.path.splitext(name)[1].lower()
            if ext in extensions:
                files.append({
                    "file_path": f.path,
                    "file_name": name,
                    "file_extension": ext,
                    "file_size": f.size,
                })
            elif f.isDir():
                # Recurse into subdirectories
                sub_files = list_document_files(f.path, extensions)
                files.extend(sub_files)
    except Exception as e:
        print(f"Warning: Could not list files at {base_path}: {e}")
    return files


def read_file_content(file_path: str) -> str:
    """Read the full text content of a file from the lakehouse."""
    try:
        content = dbutils.fs.head(file_path, maxBytes=10 * 1024 * 1024)  # 10 MB limit
        return content
    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")
        return ""

# COMMAND ----------

# MAGIC %md
# MAGIC ## Metadata Extraction

# COMMAND ----------

def extract_metadata(file_name: str, content: str) -> dict:
    """
    Extract metadata from a document.
    Returns document_type and a list of section headers found.
    """
    ext = os.path.splitext(file_name)[1].lower()

    # Determine document type from extension and content
    if ext in [".md", ".markdown"]:
        doc_type = "markdown"
    elif ext in [".txt", ".text"]:
        doc_type = "text"
    else:
        doc_type = "unknown"

    # Extract section headers (markdown headers)
    headers = []
    if doc_type == "markdown":
        header_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        for match in header_pattern.finditer(content):
            level = len(match.group(1))
            title = match.group(2).strip()
            headers.append({"level": level, "title": title})

    return {
        "document_type": doc_type,
        "section_headers": headers,
        "title": headers[0]["title"] if headers else file_name,
    }

# COMMAND ----------

# MAGIC %md
# MAGIC ## Chunking Functions

# COMMAND ----------

def approximate_token_count(text: str) -> int:
    """
    Approximate token count using whitespace splitting.
    A rough heuristic: 1 token ~ 0.75 words, or ~4 characters.
    We use word count as a reasonable approximation.
    """
    return len(text.split())


def chunk_document(
    content: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list:
    """
    Split document text into overlapping chunks using a sliding window approach.

    Parameters:
        content: Full document text
        chunk_size: Target number of tokens per chunk
        overlap: Number of overlapping tokens between chunks

    Returns:
        List of dicts with chunk_text, chunk_index, token_count
    """
    words = content.split()
    if not words:
        return []

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)

        chunks.append({
            "chunk_text": chunk_text,
            "chunk_index": chunk_index,
            "token_count": len(chunk_words),
        })

        # Advance window by (chunk_size - overlap)
        start += chunk_size - overlap
        chunk_index += 1

        # Avoid tiny trailing chunks
        if len(words) - start < overlap and start < len(words):
            # Merge remainder into the last chunk
            remaining = " ".join(words[start:])
            chunks[-1]["chunk_text"] += " " + remaining
            chunks[-1]["token_count"] += len(words) - start
            break

    return chunks


def chunk_by_sections(content: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    """
    Chunk a markdown document by sections first, then apply sliding window
    within each section. This preserves section context.
    """
    # Split on markdown headers
    section_pattern = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)
    sections = section_pattern.split(content)

    results = []
    current_header = "Introduction"

    for part in sections:
        part = part.strip()
        if not part:
            continue

        # Check if this part is a header
        if re.match(r"^#{1,6}\s+", part):
            current_header = re.sub(r"^#{1,6}\s+", "", part).strip()
            continue

        # Chunk the section content
        section_chunks = chunk_document(part, chunk_size, overlap)
        for chunk in section_chunks:
            chunk["section_header"] = current_header
            results.append(chunk)

    # Re-index chunks sequentially
    for i, chunk in enumerate(results):
        chunk["chunk_index"] = i

    return results if results else chunk_document(content, chunk_size, overlap)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Embedding Generation (Placeholder)

# COMMAND ----------

def generate_mock_embedding(text: str, dim: int = EMBEDDING_DIM) -> list:
    """
    Generate a deterministic mock embedding based on text hash.
    Useful for testing pipeline without Azure OpenAI access.
    """
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    # Convert hash to a list of floats
    embedding = []
    for i in range(dim):
        byte_idx = i % len(text_hash)
        val = int(text_hash[byte_idx], 16) / 15.0  # Normalize to [0, 1]
        embedding.append(round(val - 0.5, 6))  # Center around 0
    return embedding


def generate_real_embedding(text: str) -> list:
    """
    Generate embedding using Azure OpenAI text-embedding-ada-002.
    Requires environment variables:
        - AZURE_OPENAI_ENDPOINT
        - AZURE_OPENAI_KEY
        - AZURE_OPENAI_EMBEDDING_DEPLOYMENT
    """
    import openai

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    api_key = os.environ.get("AZURE_OPENAI_KEY", "")
    deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")

    if not endpoint or not api_key:
        raise ValueError("Azure OpenAI credentials not configured. Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY.")

    client = openai.AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2024-02-01",
    )

    response = client.embeddings.create(input=[text], model=deployment)
    return response.data[0].embedding

# COMMAND ----------

# MAGIC %md
# MAGIC ## Process Documents

# COMMAND ----------

print("Scanning for documents...")
document_files = list_document_files(UNSTRUCTURED_PATH, SUPPORTED_EXTENSIONS)
print(f"Found {len(document_files)} document(s)")

if not document_files:
    print("No documents found. Creating sample document for demonstration.")
    # Create a sample document if none exist
    sample_content = """# Manulife Group Benefits Guide

## Overview
Manulife provides comprehensive group benefits solutions for Canadian employers.
Our plans cover health, dental, vision, and disability benefits.

## Health Benefits
Extended health coverage includes prescription drugs, paramedical services,
and hospital accommodation. Coverage limits vary by plan level.

## Dental Benefits
Dental coverage includes preventive care, basic restorative, major restorative,
and orthodontic services. Annual maximums apply per covered person.

## Disability Benefits
Short-term and long-term disability coverage protects employees against
income loss due to illness or injury. Waiting periods and benefit durations
vary by plan design.

## Claims Process
Members can submit claims through the Manulife app, online portal, or paper forms.
Direct deposit is available for faster reimbursement.
"""
    document_files = [{
        "file_path": "sample://group_benefits_guide.md",
        "file_name": "group_benefits_guide.md",
        "file_extension": ".md",
        "file_size": len(sample_content),
        "_content": sample_content,
    }]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Build Chunks Table

# COMMAND ----------

all_chunks = []

for doc in document_files:
    file_name = doc["file_name"]
    file_path = doc["file_path"]
    print(f"\nProcessing: {file_name}")

    try:
        # Read content
        if "_content" in doc:
            content = doc["_content"]  # Sample document
        else:
            content = read_file_content(file_path)

        if not content:
            print(f"  Skipping (empty content)")
            continue

        # Extract metadata
        metadata = extract_metadata(file_name, content)
        print(f"  Type: {metadata['document_type']}, Sections: {len(metadata['section_headers'])}")

        # Chunk the document
        if metadata["document_type"] == "markdown":
            chunks = chunk_by_sections(content, CHUNK_SIZE, CHUNK_OVERLAP)
        else:
            chunks = chunk_document(content, CHUNK_SIZE, CHUNK_OVERLAP)

        print(f"  Chunks: {len(chunks)}")

        # Build rows
        for chunk in chunks:
            chunk_id = str(uuid.uuid4())
            section_header = chunk.get("section_header", metadata.get("title", ""))

            # Generate embedding
            if USE_REAL_EMBEDDINGS:
                try:
                    embedding = generate_real_embedding(chunk["chunk_text"])
                except Exception as emb_err:
                    print(f"  Embedding error, falling back to mock: {emb_err}")
                    embedding = generate_mock_embedding(chunk["chunk_text"])
            else:
                embedding = generate_mock_embedding(chunk["chunk_text"])

            all_chunks.append(Row(
                chunk_id=chunk_id,
                document_name=file_name,
                document_type=metadata["document_type"],
                section_header=section_header,
                chunk_text=chunk["chunk_text"],
                chunk_index=chunk["chunk_index"],
                token_count=chunk["token_count"],
                source_path=file_path,
                embedding=embedding,
            ))

    except Exception as e:
        print(f"  ERROR processing {file_name}: {e}")
        traceback.print_exc()

print(f"\nTotal chunks generated: {len(all_chunks)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write Chunks to Delta Table

# COMMAND ----------

if all_chunks:
    # Define schema explicitly for the document_chunks table
    chunk_schema = StructType([
        StructField("chunk_id", StringType(), False),
        StructField("document_name", StringType(), False),
        StructField("document_type", StringType(), True),
        StructField("section_header", StringType(), True),
        StructField("chunk_text", StringType(), False),
        StructField("chunk_index", IntegerType(), False),
        StructField("token_count", IntegerType(), False),
        StructField("source_path", StringType(), True),
        StructField("embedding", ArrayType(FloatType()), True),
    ])

    df_chunks = spark.createDataFrame(all_chunks, schema=chunk_schema)
    df_chunks = df_chunks.withColumn("_processing_timestamp", current_timestamp())

    # Write to delta table
    (
        df_chunks.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable("document_chunks")
    )

    total = df_chunks.count()
    print(f"\nWritten {total:,} chunks to document_chunks table")

    # Summary statistics
    print(f"\n{'='*60}")
    print("DOCUMENT PROCESSING SUMMARY")
    print(f"{'='*60}")
    display(
        df_chunks
        .groupBy("document_name", "document_type")
        .agg(
            {"chunk_index": "max", "token_count": "sum", "chunk_id": "count"}
        )
        .withColumnRenamed("max(chunk_index)", "max_chunk_index")
        .withColumnRenamed("sum(token_count)", "total_tokens")
        .withColumnRenamed("count(chunk_id)", "chunk_count")
    )

    # Show sample chunks
    print("\nSample chunks:")
    display(df_chunks.select("chunk_id", "document_name", "section_header", "chunk_index", "token_count").limit(10))
else:
    print("No chunks to write. Check document sources.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify Document Chunks Table

# COMMAND ----------

try:
    df_verify = spark.table("document_chunks")
    print(f"document_chunks table: {df_verify.count():,} rows")
    print(f"Columns: {df_verify.columns}")
    df_verify.printSchema()
    display(df_verify.limit(5))
except Exception as e:
    print(f"Verification failed: {e}")
