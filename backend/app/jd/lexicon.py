"""Known hard skills and the patterns that count as a mention of each.

A fixed list keeps the keyword score the same every time, without an API
key. Patterns are case-insensitive regexes; aliases point to one
canonical name so "JS" and "JavaScript" count as the same skill. Ambiguous
English words (Go, R, Rest, Swift-as-a-verb) are only matched in safe forms.
"""

from __future__ import annotations

import re

SKILLS: dict[str, list[str]] = {
    # languages
    "Python": [r"python"],
    "Java": [r"java(?!\s*script)"],
    "JavaScript": [r"javascript", r"\bjs\b", r"ecmascript", r"es6"],
    "TypeScript": [r"typescript", r"\bts\b(?=\s*[,/)]|\s+and\b)"],
    "C++": [r"c\+\+", r"\bcpp\b"],
    "C#": [r"c#", r"\.net\b", r"dotnet"],
    "C": [r"\bc(?=\s*(?:,|/|and|\(|programming))(?!\+|#)"],
    "Go": [r"golang", r"\bgo\s*\(golang\)", r"\bgo(?=\s*,\s*(?:rust|java|python|c\+\+))"],
    "Rust": [r"\brust\b"],
    "Kotlin": [r"kotlin"],
    "Swift": [r"\bswift(?:ui)?\b(?=.{0,40}\b(?:ios|xcode|apple|kotlin|objective)|\s*,)"],
    "Ruby": [r"\bruby\b"],
    "PHP": [r"\bphp\b"],
    "Scala": [r"\bscala\b"],
    "SQL": [r"\bsql\b"],
    "Bash": [r"\bbash\b", r"shell scripting"],
    "HTML": [r"\bhtml5?\b"],
    "CSS": [r"\bcss3?\b"],
    # frontend
    "React": [r"\breact(?:\.js|js)?\b(?!\s*native)"],
    "React Native": [r"react\s*native"],
    "Angular": [r"\bangular(?:js)?\b"],
    "Vue": [r"\bvue(?:\.js|js)?\b"],
    "Next.js": [r"next\.?js"],
    "Tailwind": [r"tailwind"],
    "Redux": [r"\bredux\b"],
    # backend
    "Node.js": [r"node\.?js", r"\bnode\b"],
    "Express": [r"express(?:\.js|js)?\b(?=.{0,30}\b(?:node|api|server))|express\.js"],
    "Django": [r"django"],
    "Flask": [r"\bflask\b"],
    "FastAPI": [r"fastapi"],
    "Spring": [r"spring\s*boot", r"\bspring\b(?=.{0,20}\b(?:java|framework|mvc))"],
    "REST APIs": [r"\brestful\b", r"\brest\s*apis?\b", r"\brest\b(?=\s*(?:/|and)\s*graphql)"],
    "GraphQL": [r"graphql"],
    "gRPC": [r"\bgrpc\b"],
    "Microservices": [r"micro-?services?"],
    "Distributed systems": [r"distributed\s+systems?"],
    "System design": [r"system\s+design"],
    "WebSockets": [r"web\s*sockets?"],
    "WebRTC": [r"webrtc"],
    # data stores and messaging
    "PostgreSQL": [r"postgres(?:ql)?"],
    "MySQL": [r"mysql"],
    "MongoDB": [r"mongo(?:db)?"],
    "Redis": [r"\bredis\b"],
    "Elasticsearch": [r"elastic\s*search"],
    "Kafka": [r"\bkafka\b"],
    "RabbitMQ": [r"rabbit\s*mq"],
    "DynamoDB": [r"dynamo\s*db"],
    "Snowflake": [r"snowflake"],
    # cloud and devops
    "AWS": [r"\baws\b", r"amazon\s+web\s+services"],
    "GCP": [r"\bgcp\b", r"google\s+cloud"],
    "Azure": [r"\bazure\b"],
    "Docker": [r"docker", r"containeri[sz]ation"],
    "Kubernetes": [r"kubernetes", r"\bk8s\b"],
    "Terraform": [r"terraform", r"infrastructure\s+as\s+code"],
    "CI/CD": [r"ci\s*/\s*cd", r"continuous\s+integration", r"github\s+actions", r"jenkins"],
    "Git": [r"\bgit\b", r"github", r"gitlab"],
    "Linux": [r"linux", r"\bunix\b"],
    # data and ML
    "Machine learning": [r"machine\s+learning", r"\bml\b"],
    "Deep learning": [r"deep\s+learning"],
    "LLMs": [r"\bllms?\b", r"large\s+language\s+models?", r"generative\s+ai", r"\bgenai\b"],
    "NLP": [r"\bnlp\b", r"natural\s+language\s+processing"],
    "Computer vision": [r"computer\s+vision", r"\bopencv\b"],
    "PyTorch": [r"pytorch"],
    "TensorFlow": [r"tensorflow", r"\bkeras\b"],
    "scikit-learn": [r"scikit-?learn", r"sklearn"],
    "Pandas": [r"\bpandas\b"],
    "NumPy": [r"numpy"],
    "Spark": [r"\bspark\b", r"pyspark"],
    "Airflow": [r"airflow"],
    "Data analysis": [r"data\s+analy(?:sis|tics)"],
    "Tableau": [r"tableau"],
    "Power BI": [r"power\s*bi"],
    # practices and fundamentals
    "Data structures & algorithms": [r"data\s+structures", r"\balgorithms?\b", r"\bdsa\b"],
    "OOP": [r"object[-\s]oriented", r"\boop\b"],
    "Testing": [r"unit\s+test", r"\btesting\b", r"\btdd\b", r"\bpytest\b", r"\bjest\b"],
    "Agile": [r"\bagile\b", r"\bscrum\b", r"\bkanban\b"],
    "Security": [r"\bsecurity\b", r"\boauth\b", r"authentication"],
    # mobile and games
    "Android": [r"\bandroid\b"],
    "iOS": [r"\bios\b"],
    "Unreal Engine": [r"unreal\s*engine", r"\bue[45]\b"],
    "Unity": [r"\bunity\b(?=.{0,20}\b(?:engine|3d|game|c#))|unity3d"],
}

_COMPILED = {name: [re.compile(p, re.I) for p in pats] for name, pats in SKILLS.items()}


def mentions(text: str, skill: str) -> bool:
    """True if `text` mentions `skill`. Unknown skills (e.g. ones the AI
    extracted) fall back to a whole-word match on the skill name."""
    pats = _COMPILED.get(skill)
    if pats is None:
        canon = canonical(skill)
        if canon:
            pats = _COMPILED[canon]
        else:
            escaped = re.escape(skill.strip())
            pats = [re.compile(rf"(?<![\w+#]){escaped}(?![\w+#])", re.I)]
    return any(p.search(text) for p in pats)


def canonical(name: str) -> str | None:
    """Map a free-form skill name to a lexicon entry if one matches it fully."""
    n = name.strip()
    for canon, pats in _COMPILED.items():
        if canon.lower() == n.lower() or any(p.fullmatch(n) for p in pats):
            return canon
    return None


def skills_in(text: str) -> list[str]:
    return [name for name in SKILLS if mentions(text, name)]
