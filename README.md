# AI Job Search Agent

A small Python CLI that scores a vacancy against **your** JSON profile and refuses to invent experience.

Decisions are `APPLY NOW`, `STRETCH APPLY`, or `SKIP`. Each requirement is tagged `KNOW`, `LEARN_FAST`, `LEARNABLE`, or `EXPERIENCE_GAP`. You get a current match and a 7-day match — the latter only rises when a gap is actually learnable fast.

This is the public, anonymised version of a local tool I use for UK remote applications. No CVs, inboxes, or personal contact details live in this repository.

## Features

- Save a job from a file, stdin, CLI text, or a public URL
- SQLite history and pipeline statuses (`APPROVED`, `APPLIED`, `INTERVIEW`, …)
- Heuristic analyser (no API key) or optional OpenAI-compatible LLM
- Honest application package: summary, skill order, project bullets, cover letter, interview prep
- Collect from public Arbeitnow UK and Remotive APIs, with URL de-duplication
- Closed or unverifiable listings stay out of the actionable shortlist

## Quick start

Python 3.12+.

```powershell
copy profile.example.json profile.json
python main.py init
python main.py run --file examples\sample-job.txt --title "Junior Python Automation Developer" --company "Example Ltd"
python main.py approve 1
python main.py export 1
```

Collect a batch:

```powershell
python main.py collect --limit 25
python main.py analyze-all
python main.py shortlist
```

Tests (stdlib `unittest` only):

```powershell
python -m unittest discover -s tests -v
```

Optional LLM: copy `.env.example` to `.env` and set `LLM_API_KEY`. Secrets are never written to SQLite.

## Layout

```
job_agent/     analyser, storage, sources, materials generator
tests/
examples/sample-job.txt
profile.example.json
```

`profile.json` is gitignored. Edit the example, then copy it.

## License

MIT.
