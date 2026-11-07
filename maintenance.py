"""Delete expired synthetic records; safe for a confirmed host's scheduled job."""
from config import DB_PATH,require_demo
from storage import Store

def main():
    require_demo();store=Store(DB_PATH)
    try:
        with store.transaction():
            before=store.conn.total_changes;store.prune();deleted=store.conn.total_changes-before
        print(f'Expired synthetic records deleted: {deleted}')
    finally:store.close()
if __name__=='__main__':main()
