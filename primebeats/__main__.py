import asyncio, logging, os
from .app import PrimeBeats
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
async def main():
    app=PrimeBeats()
    try: await app.run()
    finally: await app.shutdown()
if __name__=="__main__": asyncio.run(main())
    
