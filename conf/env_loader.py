import os
from pathlib import Path


def load_dotenv():
    env_path = Path(__file__).resolve().parent.parent / '.env'
    if not env_path.exists():
        return

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            # Don't overwrite existing environment variables
            if key not in os.environ:
                os.environ[key] = value
