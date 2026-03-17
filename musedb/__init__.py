"""MuseDB — AI-native file database.

Embedded usage::

    import asyncio
    from musedb import MuseDB

    async def main():
        db = MuseDB.open("./my_workspace")
        await db.init()
        await db.index()
        results = await db.search("quarterly revenue")
        print(results)
        await db.close()

    asyncio.run(main())
"""

from app.workspace import Workspace as MuseDB

__all__ = ["MuseDB"]
