from pydantic import BaseModel
from datetime import datetime
from dateutil import parser as dateparser

class RepositoryConfigSchema(BaseModel):
    name: str
    owner: str
    master_branch: str
    remote_url: str

class CommitSchema(BaseModel):
    sha: str
    author: str
    committer: str
    parents: list[str] # sha of parent(s)
    created: datetime

    @classmethod
    def from_gitea(cls, gitea_commit):
        return CommitSchema(
            sha=gitea_commit["sha"],
            author=gitea_commit["author"]["username"],
            committer=gitea_commit["committer"]["username"],
            parents=[p["sha"] for p in gitea_commit["parents"]],
            created=dateparser.isoparse(gitea_commit["created"])
        )