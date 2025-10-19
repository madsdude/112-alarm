from contextlib import contextmanager
from sqlmodel import SQLModel, Session, create_engine


engine = create_engine("sqlite:///./game.db", echo=False)


def init_db():
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session

