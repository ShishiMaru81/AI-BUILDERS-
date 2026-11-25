
"""Load private local settings before API, migrations, or worker imports."""
import os
from pathlib import Path

from dotenv import load_dotenv

_api_dir = Path(__file__).resolve().parent.parent
_env_dir = (_api_dir.parent.parent
            if _api_dir.name == 'api' and _api_dir.parent.name == 'apps'
            else _api_dir)
# Hosted service environment variables always take precedence over local files.
load_dotenv(_env_dir / '.env', override=False)


def public_demo_enabled() -> bool:
    return os.getenv('HOSTING_TIER') == 'vercel_demo'
