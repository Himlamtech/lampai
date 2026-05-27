"""Music catalog service."""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import MusicCatalogModel
from app.core.logging import get_logger

logger = get_logger("music_service")

# Seed data for initial music catalog
SEED_TRACKS = [
    {
        "id": "rain_01",
        "title": "Rain Sound",
        "type": "RAIN",
        "source_url": "https://example.com/audio/rain.mp3",
        "duration_seconds": 900,
        "is_default": True,
    },
    {
        "id": "sleep_01",
        "title": "Sleep Music",
        "type": "SLEEP",
        "source_url": "https://example.com/audio/sleep.mp3",
        "duration_seconds": 1800,
        "is_default": False,
    },
    {
        "id": "nature_01",
        "title": "Nature Sounds",
        "type": "NATURE",
        "source_url": "https://example.com/audio/nature.mp3",
        "duration_seconds": 900,
        "is_default": False,
    },
    {
        "id": "ocean_01",
        "title": "Ocean Waves",
        "type": "OCEAN",
        "source_url": "https://example.com/audio/ocean.mp3",
        "duration_seconds": 900,
        "is_default": False,
    },
    {
        "id": "meditation_01",
        "title": "Meditation",
        "type": "MEDITATION",
        "source_url": "https://example.com/audio/meditation.mp3",
        "duration_seconds": 600,
        "is_default": False,
    },
]


class MusicService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def seed_catalog(self) -> None:
        """Seed the music catalog with initial tracks if empty."""
        result = await self.session.execute(select(MusicCatalogModel).limit(1))
        if result.scalar_one_or_none() is not None:
            return  # Already seeded

        for track_data in SEED_TRACKS:
            track = MusicCatalogModel(**track_data)
            self.session.add(track)
        await self.session.commit()
        logger.info("music_catalog_seeded", count=len(SEED_TRACKS))

    async def get_tracks(self, music_type: str | None = None) -> list[MusicCatalogModel]:
        """Get tracks, optionally filtered by type."""
        query = select(MusicCatalogModel)
        if music_type:
            query = query.where(MusicCatalogModel.type == music_type.upper())
        result = await self.session.execute(query.order_by(MusicCatalogModel.title))
        return list(result.scalars().all())

    async def select_track(self, music_type: str) -> MusicCatalogModel | None:
        """Select a track matching the requested type."""
        result = await self.session.execute(
            select(MusicCatalogModel)
            .where(MusicCatalogModel.type == music_type.upper())
            .limit(1)
        )
        track = result.scalar_one_or_none()
        if track:
            return track
        # Fallback to default
        return await self.get_default_track()

    async def get_default_track(self) -> MusicCatalogModel | None:
        """Get the default track."""
        result = await self.session.execute(
            select(MusicCatalogModel).where(MusicCatalogModel.is_default == True).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_track_by_id(self, track_id: str) -> MusicCatalogModel | None:
        result = await self.session.execute(
            select(MusicCatalogModel).where(MusicCatalogModel.id == track_id)
        )
        return result.scalar_one_or_none()
