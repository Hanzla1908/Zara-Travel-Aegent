from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.job import Job

SEED_JOBS = [
    {
        "external_id": "seed:systems-limited-senior-react-developer",
        "title": "Senior React Developer",
        "company": "Systems Limited",
        "initials": "SL",
        "color": "#4F46E5",
        "location": "Lahore, Pakistan",
        "location_type": "Hybrid",
        "type": "Full-time",
        "experience": "Senior",
        "salary": "PKR 180k – 250k/mo",
        "match_score": 94.0,
        "source": "linkedin",
        "posted_days": 1,
        "description": (
            "We are looking for a Senior React Developer to join our growing engineering team. "
            "You will own entire frontend modules, drive technical architecture decisions, and mentor junior engineers.\n\n"
            "This role requires deep React expertise and a passion for writing clean, maintainable code that scales."
        ),
        "requirements": [
            "5+ years of professional React experience",
            "Strong TypeScript skills",
            "Experience with state management (Redux / Zustand)",
            "REST API integration and async patterns",
            "CI/CD experience",
            "Team leadership or mentorship experience",
        ],
        "matching_skills": ["React", "TypeScript", "CSS", "Git", "REST APIs", "Redux"],
        "missing_skills": ["Next.js", "GraphQL"],
        "tags": ["React", "TypeScript", "Redux", "Node.js"],
    },
    {
        "external_id": "seed:arbisoft-full-stack-engineer",
        "title": "Full Stack Engineer",
        "company": "Arbisoft",
        "initials": "AS",
        "color": "#059669",
        "location": "Islamabad, Pakistan",
        "location_type": "Remote",
        "type": "Full-time",
        "experience": "Mid",
        "salary": "PKR 150k – 200k/mo",
        "match_score": 87.0,
        "source": "rozee",
        "posted_days": 2,
        "description": (
            "Arbisoft is hiring Full Stack Engineers to build cutting-edge products for global clients "
            "across fintech, edtech, and SaaS domains. You will work across the entire stack with autonomy and modern tooling."
        ),
        "requirements": [
            "3+ years full stack experience",
            "React or Vue.js for the frontend",
            "Python/Django or Node.js backend",
            "PostgreSQL or MySQL",
            "AWS or cloud experience is a plus",
        ],
        "matching_skills": ["React", "Python", "PostgreSQL", "Git", "REST APIs"],
        "missing_skills": ["Django", "AWS"],
        "tags": ["React", "Python", "Django", "PostgreSQL"],
    },
    {
        "external_id": "seed:netsol-frontend-developer",
        "title": "Frontend Developer",
        "company": "Netsol Technologies",
        "initials": "NT",
        "color": "#DC2626",
        "location": "Lahore, Pakistan",
        "location_type": "On-site",
        "type": "Full-time",
        "experience": "Mid",
        "salary": "PKR 100k – 140k/mo",
        "match_score": 82.0,
        "source": "linkedin",
        "posted_days": 3,
        "description": (
            "Netsol Technologies builds enterprise-level financial software for automotive finance companies worldwide. "
            "As a Frontend Developer you will deliver pixel-perfect, performant interfaces on our flagship products."
        ),
        "requirements": [
            "3+ years JavaScript experience",
            "React or Angular",
            "CSS/SCSS expertise",
            "Unit testing with Jest",
            "Agile / Scrum methodology",
        ],
        "matching_skills": ["JavaScript", "React", "CSS", "Jest", "Agile"],
        "missing_skills": ["Angular", "SCSS"],
        "tags": ["JavaScript", "React", "CSS", "Jest"],
    },
    {
        "external_id": "seed:folio3-react-native-developer",
        "title": "React Native Developer",
        "company": "Folio3 Software",
        "initials": "F3",
        "color": "#7C3AED",
        "location": "Karachi, Pakistan",
        "location_type": "Hybrid",
        "type": "Full-time",
        "experience": "Mid",
        "salary": "PKR 120k – 160k/mo",
        "match_score": 76.0,
        "source": "rozee",
        "posted_days": 4,
        "description": (
            "Build mobile applications for clients in retail, healthcare, and logistics. "
            "You will lead mobile development from architecture through App Store / Play Store deployment."
        ),
        "requirements": [
            "2+ years React Native experience",
            "iOS and Android deployment",
            "State management (Redux / MobX)",
            "REST API integration",
            "App Store & Play Store publishing",
        ],
        "matching_skills": ["React", "JavaScript", "REST APIs", "Redux"],
        "missing_skills": ["React Native", "iOS", "Android"],
        "tags": ["React Native", "iOS", "Android", "JavaScript"],
    },
    {
        "external_id": "seed:tkxel-uiux-engineer",
        "title": "UI/UX Engineer",
        "company": "Tkxel",
        "initials": "TX",
        "color": "#EA580C",
        "location": "Lahore, Pakistan",
        "location_type": "Remote",
        "type": "Contract",
        "experience": "Mid",
        "salary": "PKR 130k – 170k/mo",
        "match_score": 71.0,
        "source": "linkedin",
        "posted_days": 5,
        "description": (
            "Bridge the gap between design and engineering. You will collaborate with product designers "
            "to implement polished, accessible interfaces and own the component library."
        ),
        "requirements": [
            "3+ years UI development",
            "Figma proficiency",
            "React or Vue",
            "Animation libraries (Framer Motion)",
            "WCAG accessibility standards",
        ],
        "matching_skills": ["React", "CSS", "JavaScript", "Figma"],
        "missing_skills": ["Vue.js", "Framer Motion", "WCAG"],
        "tags": ["React", "Figma", "CSS", "Animation"],
    },
    {
        "external_id": "seed:10pearls-software-engineer-frontend",
        "title": "Software Engineer – Frontend",
        "company": "10Pearls",
        "initials": "10",
        "color": "#0891B2",
        "location": "Islamabad, Pakistan",
        "location_type": "Hybrid",
        "type": "Full-time",
        "experience": "Senior",
        "salary": "PKR 200k – 280k/mo",
        "match_score": 68.0,
        "source": "rozee",
        "posted_days": 6,
        "description": (
            "Lead frontend engineering on large-scale digital transformation projects for US-based enterprise clients. "
            "Own entire frontend modules and drive technical decisions for complex systems."
        ),
        "requirements": [
            "5+ years React or Angular",
            "Micro-frontend architecture experience",
            "Performance optimisation at scale",
            "CI/CD pipelines",
            "Strong English communication for US clients",
        ],
        "matching_skills": ["React", "TypeScript", "Git", "REST APIs"],
        "missing_skills": ["Micro-frontends", "Angular", "CI/CD", "Webpack Config"],
        "tags": ["React", "Angular", "TypeScript", "Micro-frontends"],
    },
]


async def seed_jobs(db: AsyncSession) -> int:
    result = await db.execute(select(Job))
    if result.scalars().first():
        return 0

    jobs = [Job(**data) for data in SEED_JOBS]
    db.add_all(jobs)
    await db.commit()
    return len(jobs)
