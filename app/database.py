from sqlmodel import create_engine, SQLModel, Session, text
from app.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

def init_db():
    # Create the PostGIS extension if using a PostgreSQL backend
    if not settings.DATABASE_URL.startswith("sqlite"):
        with Session(engine) as session:
            session.exec(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            session.commit()
    # Create the tables in the database
    # Imported models will be registered here
    import app.models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    
    # Auto-seed Hospital table if empty
    from app.models import Hospital
    with Session(engine) as session:
        count = session.query(Hospital).count()
        if count == 0:
            import json
            import pathlib
            json_path = pathlib.Path(__file__).parent / "hopitals-osm.json"
            if json_path.exists():
                print(f"Auto-seeding hospitals table from {json_path}...")
                with open(json_path, "r", encoding="utf-8") as f:
                    hospitals_data = json.load(f)
                
                hospitals_to_insert = []
                for item in hospitals_data:
                    hospital = Hospital(
                        name=item.get("name"),
                        address=item.get("address"),
                        region=item.get("region"),
                        phone=item.get("phone"),
                        latitude=item.get("latitude"),
                        longitude=item.get("longitude"),
                        osm_id=item.get("osm_id"),
                        facility_type=item.get("facility_type")
                    )
                    hospitals_to_insert.append(hospital)
                
                session.add_all(hospitals_to_insert)
                session.commit()
                print(f"Successfully seeded {len(hospitals_to_insert)} hospitals.")

def get_session():
    with Session(engine) as session:
        yield session
