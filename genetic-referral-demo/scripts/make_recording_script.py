"""Render RECORDING_SCRIPT.md from the teleprompter HTML.

RECORDING_SCRIPT.md has always claimed to be generated "so the two cannot drift".
It was not -- it was hand-maintained, and by the time the ontology went in the repo
copy was two rewrites behind the artifact. This makes the claim true.

    python scripts/make_recording_script.py --html docs-teleprompter.html

Reads the same file that gets published as the Artifact, so the markdown, the repo
copy and the live teleprompter are one source.
"""
import argparse
import html
import re
import sys
from pathlib import Path

ARTIFACT = "https://claude.ai/code/artifact/6b5e7ad0-e8cd-4567-bae7-fd178dae5846"


def text(fragment):
    """HTML fragment -> plain markdown-ish prose, keeping emphasis and code."""
    s = fragment
    s = re.sub(r"<(strong|b)>(.*?)</\1>", r"**\2**", s, flags=re.S)
    s = re.sub(r"<(em|i)>(.*?)</\1>", r"*\2*", s, flags=re.S)
    s = re.sub(r'<code[^>]*>(.*?)</code>', r"`\1`", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def render(doc):
    out = ["# Screen recording script — genetic referral case-finding", ""]

    eyebrow = re.search(r'<p class="eyebrow">(.*?)</p>', doc, re.S)
    out += [
        "Generated from the teleprompter by `scripts/make_recording_script.py`,",
        "so the two cannot drift. Re-run it after any edit to `docs-teleprompter.html`.",
        "",
        f"Live: {ARTIFACT}",
        "",
        f"*{text(eyebrow.group(1))}*" if eyebrow else "",
        "",
        "The recording leads with the outcome, demonstrates the Fabric IQ experience,",
        "and only then explains the machinery underneath. Sections marked **ref** are",
        "not spoken; they exist so you can answer \"how does that actually work?\"",
        "precisely rather than approximately.",
        "",
        "> Quoted text is what you say. *Italic* is what you do.",
        "",
    ]

    # The prep blocks above the first section, in document order.
    for block in re.finditer(r'<div class="prep">(.*?)</div>', doc, re.S):
        body = block.group(1)
        head = re.search(r"<h2[^>]*>(.*?)</h2>", body, re.S)
        out += [f"## {text(head.group(1))}" if head else "##", ""]
        for li in re.findall(r"<li>(.*?)</li>", body, re.S):
            out.append(f"- {text(li)}")
        for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            cells = [text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            if cells:
                out.append(f"- **{cells[0]}** — {' '.join(cells[1:])}")
        for pre in re.findall(r"<pre>(.*?)</pre>", body, re.S):
            out += ["", "```", html.unescape(re.sub("<[^>]+>", "", pre)).strip(), "```"]
        out.append("")

    for sec in re.finditer(r'<section id="([^"]+)">(.*?)</section>', doc, re.S):
        sid, body = sec.group(1), sec.group(2)
        clock = re.search(r'<span class="time">(.*?)</span>', body, re.S)
        head = re.search(r"<h2[^>]*>(.*?)</h2>", body, re.S)
        stamp = text(clock.group(1)) if clock else ""
        out += [f"## {stamp} · {text(head.group(1))}" if head else f"## {stamp}", ""]

        # Walk the section in document order so stage directions stay interleaved
        # with the lines they belong to -- the order is the whole point of the file.
        for m in re.finditer(
                r'<p class="(say|do|beat|note)">(.*?)</p>|<pre>(.*?)</pre>', body, re.S):
            if m.group(3) is not None:
                out += ["", "```", html.unescape(re.sub("<[^>]+>", "", m.group(3))).strip(),
                        "```", ""]
                continue
            kind, content = m.group(1), text(m.group(2))
            if kind == "say":
                out += [f"> {content}", ""]
            elif kind == "do":
                out += [f"*{content}*", ""]
            elif kind == "beat":
                out += [f"`{content}`", ""]
            else:
                out += [f"**Note.** {content}", ""]
        out.append("")

    spoken = sum(len(text(s).split())
                 for s in re.findall(r'<p class="say">(.*?)</p>', doc, re.S))
    out += ["---", "",
            f"{spoken} spoken words — about {spoken / 140:.0f} minutes of narration at a "
            "measured pace, nearer 18 recorded once page loads and query runs are in.", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--html", default="docs-teleprompter.html")
    ap.add_argument("--out", default="RECORDING_SCRIPT.md")
    args = ap.parse_args()

    src = Path(args.html)
    if not src.exists():
        sys.exit(f"no such file: {src}")
    md = render(src.read_text(encoding="utf-8"))
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"{src} -> {args.out}  ({len(md.splitlines())} lines)")


if __name__ == "__main__":
    main()
