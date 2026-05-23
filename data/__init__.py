from .database import SuperNewsAnalyzer
from .prices import get_prices, validate_ticker

def list_databases():
    from pathlib import Path
    db_folder = Path.cwd() / "data" / "news_databases"
    db_folder.mkdir(parents=True, exist_ok=True)
    dbs = list(db_folder.glob("*.db"))
    return [f.name for f in dbs]

def cleanup_all_dbs():
    """🗑️ Pulizia TOTALE"""
    from pathlib import Path
    db_folder = Path.cwd() / "data" / "news_databases"
    deleted = 0
    if db_folder.exists():
        for db_file in db_folder.glob("*.db"):
            db_file.unlink(missing_ok=True)
            deleted += 1
        print(f"Puliti {deleted} DB")
    return deleted

__all__ = ['SuperNewsAnalyzer', 'get_prices', 'validate_ticker', 'list_databases', 'cleanup_all_dbs']