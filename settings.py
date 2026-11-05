"""User data lives outside the app folder (default ~/GapFinder, override with GAPFINDER_HOME) so updating the app never loses projects or keys."""
import os, json
from pathlib import Path
KEYS = ["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", "openai/gpt-oss-120b", "bolt://localhost:7687", "neo4j", "neo4jneo4j", "neo4j", "abderrahmene.benabdelkader@univ-tlemcen.dz", "EMBED_MODEL", "GAPFINDER_USE_NEO4J"]
def home(): d = Path(os.getenv("GAPFINDER_HOME") or Path.home() / "GapFinder"); d.mkdir(parents=True, exist_ok=True); return d
def projects_dir(): d = home() / "projects"; d.mkdir(parents=True, exist_ok=True); return d
def load():
    f = home() / "settings.json"
    try: return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError: return {}
def save(d):
    f = home() / "settings.json"; cur = load(); cur.update({k: v for k, v in d.items() if k in KEYS}); f.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    try: os.chmod(f, 0o600)
    except OSError: pass
def apply():
    """Settings saved in the app win over .env / shell variables."""
    for k, v in load().items():
        if v: os.environ[k] = str(v)
