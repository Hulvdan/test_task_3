from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_db: str = Field(str)
    postgres_host: str = Field(str)
    postgres_port: int = Field(int)
    postgres_user: str = Field(str)
    postgres_password: str = Field(str)

    @property
    def postgres_dsn(self) -> str:
        return "postgresql+asyncpg://{}:{}@{}:{}/{}".format(
            self.postgres_user,
            self.postgres_db,
            self.postgres_host,
            self.postgres_port,
            self.postgres_password,
        )


settings = Settings(_env_file=".env")
