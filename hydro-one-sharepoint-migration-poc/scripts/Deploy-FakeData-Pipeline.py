"""Hydro One synthetic end-to-end migration test.

Creates and runs an ADF pipeline that:
  1. Inserts 5 FAKE library rows into dbo.MigrationControl via Script activity
  2. Lookup pending FAKE_% rows
  3. ForEach: Copy activity emits inline synthetic CSV content -> ADLS at
     /sharepoint-migration/<LibraryName>/data.csv
  4. Updates each row to Status='Completed' with metrics populated

Demonstrates the same orchestration pattern (SQL -> ADF ForEach -> ADLS) as the
real migration, without any SharePoint or Graph API dependency.
"""
import subprocess, json, urllib.request, time, sys, io
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def sh(c): return subprocess.check_output(c, shell=True).decode().strip()

SUB    = "671b1321-4407-420b-b877-97cd40ba898a"
RG     = "rg-hydroone-migration-test"
ADF    = "adf-hydroone-migration-test"

TOKEN = sh("az account get-access-token --resource https://management.azure.com --query accessToken -o tsv")
BASE = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.DataFactory/factories/{ADF}"
API_VERSION = "2018-06-01"

def arm(method, path, body=None, timeout=120):
    url = f"{BASE}{path}?api-version={API_VERSION}"
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower():v for k,v in r.headers.items()}, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower():v for k,v in (e.headers.items() if e.headers else [])}, e.read().decode()

# ---------- 1. Create ADLS fake-file sink dataset ----------
print("== Creating dataset DS_ADLS_FakeFile_Sink ==", flush=True)
fake_sink = {
    "properties": {
        "linkedServiceName": {"referenceName": "LS_ADLS_Gen2", "type": "LinkedServiceReference"},
        "parameters": {"libraryName": {"type": "string"}},
        "annotations": ["synthetic-test"],
        "type": "DelimitedText",
        "typeProperties": {
            "location": {
                "type": "AzureBlobFSLocation",
                "fileName": "data.csv",
                "folderPath": {
                    "value": "@concat('sharepoint-migration/', dataset().libraryName)",
                    "type": "Expression"
                },
                "fileSystem": "sharepoint-migration"
            },
            "columnDelimiter": ",",
            "escapeChar": "\\",
            "firstRowAsHeader": True,
            "quoteChar": "\""
        },
        "schema": []
    }
}
s, h, b = arm("PUT", "/datasets/DS_ADLS_FakeFile_Sink", fake_sink)
print(f"  HTTP {s}: {b[:200] if s>=400 else 'OK'}", flush=True)

# ---------- 2. Create pipeline ----------
print("\n== Creating pipeline PL_FakeData_E2E_Test ==", flush=True)
SEED_SQL = """DELETE FROM dbo.MigrationControl WHERE LibraryName LIKE 'FAKE_%';
INSERT INTO dbo.MigrationControl
    (SiteUrl, LibraryName, SiteTitle, LibraryTitle, Status, FileCount, FolderCount,
     TotalSizeBytes, LargestFileSizeBytes, RetryCount, Priority, EnableIncrementalSync)
VALUES
    ('https://m365x52073746.sharepoint.com/sites/FakeSite1', 'FAKE_Documents',
     'Fake Site 1 - Engineering', 'Documents Library', 'Pending', 5, 1, 524288, 102400, 0, 100, 1),
    ('https://m365x52073746.sharepoint.com/sites/FakeSite2', 'FAKE_Reports',
     'Fake Site 2 - Finance', 'Reports', 'Pending', 3, 0, 262144, 92160, 0, 100, 1),
    ('https://m365x52073746.sharepoint.com/sites/FakeSite3', 'FAKE_Archive',
     'Fake Site 3 - Legal', 'Archive', 'Pending', 8, 2, 1048576, 524288, 0, 100, 1),
    ('https://m365x52073746.sharepoint.com/sites/FakeSite4', 'FAKE_HR_Policies',
     'HR Portal', 'HR Policies', 'Pending', 12, 3, 786432, 81920, 0, 50, 1),
    ('https://m365x52073746.sharepoint.com/sites/FakeSite5', 'FAKE_Project_Specs',
     'Project Portal', 'Specs', 'Pending', 4, 0, 131072, 65536, 0, 100, 1);"""

UPDATE_SQL = """UPDATE dbo.MigrationControl
SET Status='Completed',
    StartTime=DATEADD(SECOND, -60, GETUTCDATE()),
    EndTime=GETUTCDATE(),
    MigratedFileCount=FileCount,
    MigratedSizeBytes=TotalSizeBytes,
    FailedFileCount=0,
    BatchId='FAKE-BATCH-' + FORMAT(GETUTCDATE(), 'yyyyMMdd-HHmmss')
WHERE Id=@{item().Id}"""

FAKE_CONTENT_SQL = """SELECT
    CAST(row_num AS NVARCHAR(10)) AS file_id,
    'synthetic_file_' + CAST(row_num AS NVARCHAR(10)) + '.txt' AS file_name,
    'Synthetic content row ' + CAST(row_num AS NVARCHAR(10)) + ' of library @{item().LibraryName}' AS content,
    FORMAT(GETUTCDATE(), 'yyyy-MM-dd HH:mm:ss') AS generated_at,
    '@{item().SiteUrl}' AS source_site,
    '@{item().LibraryName}' AS library_name
FROM (VALUES (1),(2),(3),(4),(5),(6),(7),(8),(9),(10)) AS v(row_num)"""

pipeline = {
    "properties": {
        "description": "Synthetic E2E test: seeds fake control-table rows and generates fake files in ADLS. No SharePoint dependency. Use to validate the SQL <-> ADF <-> ADLS plumbing.",
        "activities": [
            {
                "name": "Insert_FakeRows",
                "type": "Script",
                "linkedServiceName": {"referenceName": "LS_AzureSqlDatabase", "type": "LinkedServiceReference"},
                "policy": {"timeout": "0.00:05:00", "retry": 1, "retryIntervalInSeconds": 30, "secureOutput": False, "secureInput": False},
                "userProperties": [],
                "typeProperties": {
                    "scripts": [{"type": "Query", "text": SEED_SQL}],
                    "scriptBlockExecutionTimeout": "02:00:00"
                }
            },
            {
                "name": "Lookup_FakePending",
                "type": "Lookup",
                "dependsOn": [{"activity": "Insert_FakeRows", "dependencyConditions": ["Succeeded"]}],
                "policy": {"timeout": "0.00:05:00", "retry": 2, "retryIntervalInSeconds": 30},
                "typeProperties": {
                    "source": {
                        "type": "AzureSqlSource",
                        "sqlReaderQuery": "SELECT Id, SiteUrl, LibraryName, FileCount, TotalSizeBytes FROM dbo.MigrationControl WHERE LibraryName LIKE 'FAKE_%' AND Status = 'Pending'",
                        "queryTimeout": "00:02:00",
                        "partitionOption": "None"
                    },
                    "dataset": {
                        "referenceName": "DS_SQL_MigrationControl",
                        "type": "DatasetReference",
                        "parameters": {"SchemaName": "dbo", "TableName": "MigrationControl"}
                    },
                    "firstRowOnly": False
                }
            },
            {
                "name": "ForEach_FakeLibrary",
                "type": "ForEach",
                "dependsOn": [{"activity": "Lookup_FakePending", "dependencyConditions": ["Succeeded"]}],
                "typeProperties": {
                    "items": {"value": "@activity('Lookup_FakePending').output.value", "type": "Expression"},
                    "isSequential": False,
                    "batchCount": 3,
                    "activities": [
                        {
                            "name": "Copy_FakeFiles_To_ADLS",
                            "type": "Copy",
                            "policy": {"timeout": "0.00:10:00", "retry": 1, "retryIntervalInSeconds": 30},
                            "typeProperties": {
                                "source": {
                                    "type": "AzureSqlSource",
                                    "sqlReaderQuery": {"value": FAKE_CONTENT_SQL, "type": "Expression"},
                                    "queryTimeout": "00:02:00",
                                    "partitionOption": "None"
                                },
                                "sink": {
                                    "type": "DelimitedTextSink",
                                    "storeSettings": {"type": "AzureBlobFSWriteSettings"},
                                    "formatSettings": {"type": "DelimitedTextWriteSettings", "quoteAllText": True, "fileExtension": ".csv"}
                                },
                                "enableStaging": False
                            },
                            "inputs": [{
                                "referenceName": "DS_SQL_MigrationControl",
                                "type": "DatasetReference",
                                "parameters": {"SchemaName": "dbo", "TableName": "MigrationControl"}
                            }],
                            "outputs": [{
                                "referenceName": "DS_ADLS_FakeFile_Sink",
                                "type": "DatasetReference",
                                "parameters": {"libraryName": {"value": "@item().LibraryName", "type": "Expression"}}
                            }]
                        },
                        {
                            "name": "Mark_Completed",
                            "type": "Script",
                            "dependsOn": [{"activity": "Copy_FakeFiles_To_ADLS", "dependencyConditions": ["Succeeded"]}],
                            "linkedServiceName": {"referenceName": "LS_AzureSqlDatabase", "type": "LinkedServiceReference"},
                            "policy": {"timeout": "0.00:02:00", "retry": 1, "retryIntervalInSeconds": 15},
                            "typeProperties": {
                                "scripts": [{"type": "Query", "text": {"value": UPDATE_SQL, "type": "Expression"}}],
                                "scriptBlockExecutionTimeout": "02:00:00"
                            }
                        }
                    ]
                }
            }
        ],
        "annotations": ["synthetic-test", "hydro-one", "no-sharepoint"],
        "folder": {"name": "SharePoint Migration"}
    }
}
s, h, b = arm("PUT", "/pipelines/PL_FakeData_E2E_Test", pipeline)
print(f"  HTTP {s}: {b[:300] if s>=400 else 'OK'}", flush=True)
if s >= 400: sys.exit(1)

# ---------- 3. Trigger ----------
print("\n== Triggering PL_FakeData_E2E_Test ==", flush=True)
s, h, b = arm("POST", "/pipelines/PL_FakeData_E2E_Test/createRun", body={})
print(f"  HTTP {s}: {b[:300]}", flush=True)
if s == 200:
    run_id = json.loads(b)["runId"]
    print(f"  Run ID: {run_id}", flush=True)
else:
    sys.exit(2)

# Save run id for monitoring
with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\hydroone_fake_runid.txt","w") as f:
    f.write(run_id)
print(f"\n== Run started: {run_id}  --  monitor via 'az datafactory pipeline-run show' ==", flush=True)
