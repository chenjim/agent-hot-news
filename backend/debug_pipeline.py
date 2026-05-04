import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from app.database import SessionLocal
from app.models.models import Article, HotEvent
from app.ai_pipeline.pipeline import AIPipeline

async def main():
    db = SessionLocal()
    try:
        unprocessed = db.query(Article).filter(Article.is_processed == False).count()
        print(f'[DB] Unprocessed articles: {unprocessed}')
        
        if unprocessed == 0:
            print('No articles to process')
            return
        
        print('[PIPELINE] Starting with full batch...')
        pipeline = AIPipeline(db)
        await pipeline.run(max_articles=500)
        
        events = db.query(HotEvent).count()
        processed = db.query(Article).filter(Article.is_processed == True).count()
        print(f'[RESULT] Events: {events}, Processed: {processed}')
        
    except Exception as e:
        print(f'\n[ERROR] {type(e).__name__}: {e}')
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
