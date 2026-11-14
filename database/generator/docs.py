"""Writes docs/data_dictionary.md, docs/erd.md and docs/schema.sql from the schema (single source of truth)."""
import os
from .schema import SCHEMA
from .export import ddl

TYPE_DOC = {"TEXT": "text", "INTEGER": "integer", "REAL": "decimal", "DATE": "date (YYYY-MM-DD)",
            "TIMESTAMP": "timestamp (ISO-8601 UTC, ...Z)", "BOOLEAN": "boolean (0/1)"}


def data_dictionary():
    out = ["# Data dictionary", "", "Generated from `database/generator/schema.py`. Every table has a single-column primary key; "
           "every relationship has a foreign key. Timestamps are UTC. `Req` = required (NOT NULL).", ""]
    for name, spec in SCHEMA.items():
        out += [f"## {name} (`{spec['file']}`)", "", spec["desc"], "", f"* **Primary key:** `{', '.join(spec['pk'])}`",
                f"* **Cardinality:** {spec['cardinality']}", "",
                "| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |", "|---|---|---|---|---|---|---|---|"]
        for nm, typ, req, allowed, unit, uniq, rule, fk in spec["cols"]:
            al = ", ".join(str(a) for a in allowed) if allowed else ""
            if len(al) > 90:
                al = al[:87] + "..."
            out.append(f"| `{nm}` | {TYPE_DOC[typ]} | {'yes' if req else 'no'} | {al} | {unit or ''} | {'yes' if uniq else ''} | "
                       f"{rule.replace('|', '/')} | {fk or ''} |")
        out.append("")
    return "\n".join(out)


def erd():
    lines = ["# Entity-relationship diagram", "", "```mermaid", "erDiagram"]
    rel = [
        ("Course", "||--o{", "Skill", "owns"), ("Course", "||--o{", "ContentItem", "offers"),
        ("Skill", "||--o{", "SkillPrerequisite", "requires"), ("Skill", "||--o{", "SkillPrerequisite", "is prerequisite in"),
        ("ContentItem", "||--|{", "ContentSkill", "maps"), ("Skill", "||--o{", "ContentSkill", "taught by"),
        ("Learner", "||--o{", "LearningPath", "enrols"), ("Course", "||--o{", "LearningPath", "followed in"),
        ("LearningPath", "||--|{", "LearningPathEvent", "history"), ("Learner", "||--o{", "Attempt", "makes"),
        ("ContentItem", "||--o{", "Attempt", "attempted in"), ("LearningPath", "||--o{", "Attempt", "contains"),
        ("Attempt", "||--o{", "AssessmentResult", "evidence"), ("Skill", "||--o{", "AssessmentResult", "measured"),
        ("Learner", "||--o{", "Recommendation", "receives"), ("LearningPath", "||--o{", "Recommendation", "for"),
        ("ContentItem", "|o--o{", "Recommendation", "suggests"), ("Recommendation", "|o--o{", "Attempt", "followed by"),
        ("Recommendation", "|o--o|", "LearningPathEvent", "assigned as step"),
    ]
    for a, c, b, label in rel:
        lines.append(f"  {a} {c} {b} : \"{label}\"")
    for name, spec in SCHEMA.items():
        lines.append(f"  {name} {{")
        for nm, typ, req, allowed, unit, uniq, rule, fk in spec["cols"][:6]:
            tag = "PK" if nm in spec["pk"] else "FK" if fk else ""
            lines.append(f"    {typ.lower()} {nm} {tag}".rstrip())
        lines.append("  }")
    lines += ["```", "", "Many-to-many relationships use bridge tables: **ContentSkill** (ContentItem N:M Skill) and "
              "**SkillPrerequisite** (Skill N:M Skill, a directed acyclic graph). Optional relationships: `Recommendation.content_id` "
              "(null for escalations), `Attempt.recommendation_id`, `Attempt.submitted_at` (abandoned), `Learner.withdrawn_at`, "
              "`ContentItem.published_at/retired_at`, `SkillPrerequisite.effective_to`.", ""]
    return "\n".join(lines)


def write_docs(docs_dir):
    os.makedirs(docs_dir, exist_ok=True)
    for fn, text in (("data_dictionary.md", data_dictionary()), ("erd.md", erd()), ("schema.sql", ddl())):
        with open(os.path.join(docs_dir, fn), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
