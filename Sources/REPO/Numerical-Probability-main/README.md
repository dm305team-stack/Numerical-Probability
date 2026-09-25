# Numerical Probability

Native macOS port of the **NUMERICAL PROBABILITY** custom GPT: a
quantitative-statistics assistant that reads `Base-Secuence.pdf`, validates
randomness vs. determinism with real Python (chi-square, runs tests, Benford,
Monte Carlo via Anthropic's server-side code execution), generates new
sequences of double numbers with computed probabilities, and produces a
downloadable PDF report.

Built with SwiftUI + Swift Package Manager only — **no Xcode required**.

## Run

```sh
# Dev loop (debug, from this folder):
swift run

# Real app (release bundle in dist/, signed ad-hoc, launches focused):
Scripts/bundle.sh release --run
```

First launch asks for your Anthropic API key (stored in the macOS Keychain).
For the dev loop you can instead export `ANTHROPIC_API_KEY` — debug builds
read it before the Keychain, which avoids the re-prompt that ad-hoc signing
causes after every rebuild.

## Knowledge

PDFs in `Knowledge/` load automatically at launch:

- `Base-Secuence.pdf` — required; the pattern source (filename must start
  with "base")
- any other PDFs — attached as supporting reference material

Replace or add documents with the **Import PDF** button or by dragging PDFs
onto the window. Per-document limit: 100 pages (API constraint).

## Flow

1. **Analyze & Generate** runs the GPT's full 7-step workflow in one turn:
   extract sequences → validate randomness → detect patterns → generate
   sequences → compute probabilities → report → PDF.
2. The report streams live; code-execution phases show as status
   ("Running Python…"). Long runs auto-resume across server `pause_turn`
   rounds.
3. Final sequences appear as a card (parsed from the model's
   `<final_sequences>` block); **Export PDF** downloads the sandbox-generated
   report via the Files API.
4. The chat bar asks follow-ups on the same conversation — the sandbox
   container is reused, so "regenerate the PDF with 10 sequences" works.

## Cost notes

- Model: `claude-opus-4-8`, streaming, adaptive thinking.
- The 4 knowledge PDFs (~91 pages) are sent as document blocks with a 1-hour
  cache breakpoint: written to cache once per hour of use, re-read at ~0.1×
  input price on every turn (analysis runs are code-execution-heavy).

## Layout

```
Knowledge/            knowledge PDFs (auto-loaded)
Support/Info.plist    bundle metadata
Scripts/bundle.sh     build + assemble + codesign dist/NumericalProbability.app
Sources/NumericalProbability/
  Models/             JSONValue (lossless block passthrough), API types,
                      SSE events, run state machine + sequence parser
  Services/           AnthropicClient (SSE), MessageAccumulator, Keychain,
                      Files API downloader, PDF exporter
  Views/              Main / Report / Sequences / Chat / Settings
  Prompts.swift       embedded GPT system prompt + kickoff contract
  AppModel.swift      orchestration: analyze, pause_turn loop, chat, export
```
