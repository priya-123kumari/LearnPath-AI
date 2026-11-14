"""Reference values: domains, course titles, topics, formats, name pools. All synthetic."""
from backend.config import ASSESSED, EVIDENCE_WEIGHT, REASON_CODES  # noqa: F401  (business rules live in the backend tier)

# domain -> (code prefix, [(course title, [4 topics]) x 5 in learning order])
DOMAINS = [
    ("Data Science", "DS", [
        ("Python for Data", ["Python Syntax", "Data Structures", "Functions", "File I/O"]),
        ("Data Wrangling", ["DataFrames", "Data Cleaning", "Joins and Reshaping", "Time Series Handling"]),
        ("Applied Statistics", ["Descriptive Statistics", "Probability", "Hypothesis Testing", "Regression"]),
        ("Machine Learning", ["Supervised Learning", "Model Evaluation", "Feature Engineering", "Unsupervised Learning"]),
        ("Deep Learning", ["Neural Networks", "Convolutional Networks", "Sequence Models", "Model Deployment"]),
    ]),
    ("Software Engineering", "SE", [
        ("Programming Fundamentals", ["Variables and Types", "Control Flow", "Debugging", "Unit Testing"]),
        ("Object-Oriented Design", ["Classes and Objects", "Inheritance", "Interfaces", "Design Patterns"]),
        ("Algorithms", ["Arrays and Lists", "Trees and Graphs", "Sorting and Searching", "Complexity Analysis"]),
        ("Web Development", ["HTTP and REST", "Frontend Frameworks", "Relational Databases", "Authentication"]),
        ("Software Architecture", ["Microservices", "Scalability", "Observability", "System Design"]),
    ]),
    ("Cloud and DevOps", "CD", [
        ("Linux Essentials", ["Shell Commands", "File Permissions", "Process Management", "Networking Basics"]),
        ("Version Control", ["Git Workflows", "Branching Strategies", "Code Review", "CI Pipelines"]),
        ("Containers", ["Container Images", "Container Networking", "Orchestration", "Package Charts"]),
        ("Cloud Platforms", ["Compute Services", "Storage Services", "Identity and Access", "Cost Management"]),
        ("Infrastructure as Code", ["Declarative Provisioning", "Configuration Management", "GitOps", "Site Reliability"]),
    ]),
    ("Cybersecurity", "CS", [
        ("Security Foundations", ["Threat Modeling", "Cryptography Basics", "Security Policies", "Risk Assessment"]),
        ("Network Security", ["Firewalls", "Intrusion Detection", "Tunneling", "Wireless Security"]),
        ("Application Security", ["Secure Coding", "Web Vulnerabilities", "API Security", "Dependency Scanning"]),
        ("Security Operations", ["Log Analysis", "Incident Response", "Threat Hunting", "Event Correlation"]),
        ("Offensive Security", ["Reconnaissance", "Exploitation", "Privilege Escalation", "Security Reporting"]),
    ]),
    ("Product and Design", "PD", [
        ("Design Thinking", ["User Research", "Personas", "Journey Mapping", "Ideation"]),
        ("UX Design", ["Wireframing", "Prototyping", "Usability Testing", "Information Architecture"]),
        ("UI Design", ["Typography", "Color Theory", "Layout Systems", "Design Systems"]),
        ("Product Management", ["Roadmapping", "Prioritization", "Product Metrics", "Stakeholder Management"]),
        ("Growth Strategy", ["Experimentation", "Funnel Analysis", "Pricing", "Retention"]),
    ]),
]
TIER_LABELS = ["Foundations of", "Core", "Applied", "Advanced", "Expert"]
COURSE_LEVELS = ["INTRODUCTORY", "INTRODUCTORY", "INTERMEDIATE", "INTERMEDIATE", "ADVANCED"]

FORMATS = ["VIDEO", "READING", "QUIZ", "EXERCISE", "INTERACTIVE", "PROJECT"]
FORMAT_MIX = [0.25, 0.20, 0.25, 0.15, 0.10, 0.05]
MAX_SCORE = {"QUIZ": 20, "EXERCISE": 50, "INTERACTIVE": 10, "PROJECT": 100}
MINUTES = {"VIDEO": 12, "READING": 15, "QUIZ": 10, "EXERCISE": 25, "INTERACTIVE": 15, "PROJECT": 90}
LEARNING_GAIN = {"VIDEO": 0.5, "READING": 0.5, "QUIZ": 0.7, "EXERCISE": 1.0, "INTERACTIVE": 0.8, "PROJECT": 1.4}
TITLE_SUFFIX = {"VIDEO": "Video Lesson", "READING": "Reading", "QUIZ": "Practice Quiz", "EXERCISE": "Hands-on Exercise",
                "INTERACTIVE": "Interactive Lab", "PROJECT": "Mini Project"}


PRIOR_LEVELS = ["NOVICE", "INTERMEDIATE", "ADVANCED"]
PRIOR_MIX = [0.55, 0.30, 0.15]
COUNTRIES = ["IN", "US", "GB", "NG", "BR", "DE", "PH", "CA", "KE", "ID", "MX", "AU"]
COUNTRY_MIX = [0.30, 0.18, 0.08, 0.07, 0.07, 0.05, 0.05, 0.05, 0.04, 0.04, 0.04, 0.03]
FIRST = ["Aarav", "Maya", "Leo", "Zara", "Ibrahim", "Sofia", "Kenji", "Amara", "Lucas", "Priya", "Noah", "Chen", "Elena", "Omar",
         "Grace", "Ravi", "Hana", "Mateo", "Ada", "Kofi", "Lina", "Arjun", "Nia", "Ethan", "Yara", "Diego", "Mei", "Tariq",
         "Isla", "Sam", "Anika", "Felix", "Zoe", "Rohan", "Lea", "Jonas", "Aisha", "Theo", "Ines", "Kai"]
LAST = ["Sharma", "Okafor", "Silva", "Nguyen", "Muller", "Haddad", "Tanaka", "Mensah", "Garcia", "Patel", "Kim", "Rossi", "Ali",
        "Novak", "Fischer", "Costa", "Ibrahim", "Lopez", "Wang", "Kowalski", "Ahmed", "Santos", "Mwangi", "Singh", "Dubois",
        "Hughes", "Reyes", "Sato", "Bauer", "Kaur"]
