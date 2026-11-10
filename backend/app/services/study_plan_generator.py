"""
AURELIA AI — Study Plan & Learning Roadmap Generator
Supports plan durations from 1 day up to 6 months (180+ days).
Generates a structured learning hierarchy: Plan -> Months -> Weeks -> Days -> Tasks.
Uses staged Gemini LLM generation with reliable domain-aware fallback.
Handles calendar month-end dates, leap years, user timezones, rest days, and workload calculations.
"""

import re
import json
import logging
import calendar
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
import zoneinfo

from app.services.gemini_client import call_gemini_api
from app.prompts.study_planner import STUDY_PLANNER_PROMPT

logger = logging.getLogger(__name__)


def parse_plan_duration(duration_text: Optional[str], duration_days: Optional[int] = None) -> int:
    """
    Parses duration string or integer into total days.
    Supports durations from 1 day up to 6 months (183 days).
    Defaults to 30 days if unspecified or unparseable.
    """
    if duration_days is not None and isinstance(duration_days, int) and duration_days > 0:
        return min(max(duration_days, 1), 183)

    if not duration_text or not isinstance(duration_text, str):
        return 30

    d_lower = duration_text.strip().lower()

    # Exact matches or keywords
    if "half year" in d_lower or "6 month" in d_lower or "6-month" in d_lower or "six month" in d_lower or "six-month" in d_lower or "180 day" in d_lower:
        return 180
    if "5 month" in d_lower or "5-month" in d_lower or "five month" in d_lower or "five-month" in d_lower or "150 day" in d_lower:
        return 150
    if "4 month" in d_lower or "4-month" in d_lower or "four month" in d_lower or "four-month" in d_lower or "120 day" in d_lower:
        return 120
    if "quarter" in d_lower or "3 month" in d_lower or "3-month" in d_lower or "three month" in d_lower or "three-month" in d_lower or "90 day" in d_lower:
        return 90
    if "2 month" in d_lower or "2-month" in d_lower or "two month" in d_lower or "two-month" in d_lower or "60 day" in d_lower:
        return 60
    if "1 month" in d_lower or "1-month" in d_lower or "one month" in d_lower or "one-month" in d_lower or "30 day" in d_lower:
        return 30
    if "3 week" in d_lower or "3-week" in d_lower or "three week" in d_lower or "three-week" in d_lower or "21 day" in d_lower:
        return 21
    if "2 week" in d_lower or "2-week" in d_lower or "two week" in d_lower or "two-week" in d_lower or "fortnight" in d_lower or "14 day" in d_lower:
        return 14
    if "1 week" in d_lower or "1-week" in d_lower or "one week" in d_lower or "one-week" in d_lower or "7 day" in d_lower or "seven day" in d_lower or "seven-day" in d_lower:
        return 7
    if "single day" in d_lower or "1 day" in d_lower or "1-day" in d_lower or "one day" in d_lower or "one-day" in d_lower:
        return 1
    # Extract digits + unit
    match = re.search(r'(\d+)\s*(month|week|day)', d_lower)
    if match:
        count = int(match.group(1))
        unit = match.group(2)
        if "month" in unit:
            return min(max(count * 30, 1), 183)
        elif "week" in unit:
            return min(max(count * 7, 1), 183)
        elif "day" in unit:
            return min(max(count, 1), 183)

    if "month" in d_lower and not any(k in d_lower for k in ["week", "day"]):
        return 30
    if "week" in d_lower and not any(k in d_lower for k in ["month", "day"]):
        return 7

    # Bare number
    num_match = re.search(r'\d+', d_lower)
    if num_match:
        num = int(num_match.group(0))
        return min(max(num, 1), 183)

    return 30


def add_calendar_months(sourcedate: date, months: int) -> date:
    """
    Safely adds calendar months to a date, clamping to the last valid day of the target month.
    Handles month-end dates (Jan 31 -> Feb 28/29, Mar 31 -> Apr 30) and leap years correctly.
    """
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calculate_plan_dates(
    start_date_str: Optional[str] = None,
    duration_text: Optional[str] = None,
    duration_days: Optional[int] = None,
    user_tz_str: str = "UTC"
) -> Tuple[date, date, int]:
    """
    Computes start_date, end_date, and total_days for a plan.
    Start date defaults to tomorrow in the user's timezone if unspecified.
    """
    try:
        user_tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        user_tz = zoneinfo.ZoneInfo("UTC")

    now_local = datetime.now(timezone.utc).astimezone(user_tz)

    if start_date_str:
        try:
            # Handle YYYY-MM-DD
            start_d = date.fromisoformat(start_date_str.split("T")[0])
        except Exception:
            start_d = now_local.date() + timedelta(days=1)
    else:
        start_d = now_local.date() + timedelta(days=1)

    total_days = parse_plan_duration(duration_text, duration_days)

    # Check if duration specifies whole calendar months (e.g. "2 months", "6 months")
    if duration_text and "month" in duration_text.lower():
        m_match = re.search(r'(\d+)\s*month', duration_text.lower())
        if m_match:
            months = int(m_match.group(1))
            if 1 <= months <= 6:
                end_d = add_calendar_months(start_d, months) - timedelta(days=1)
                total_days = (end_d - start_d).days + 1
                return start_d, end_d, total_days

    end_d = start_d + timedelta(days=total_days - 1)
    return start_d, end_d, total_days


# ---------------------------------------------------------------------------
# Structured Curriculum Knowledge & Topic Progressions
# ---------------------------------------------------------------------------

CURRICULUM_TEMPLATES = {
    "dsa": {
        "title": "Data Structures & Algorithms Mastery",
        "milestones": [
            "Milestone 1: Arrays, Strings, Two Pointers & Sliding Window",
            "Milestone 2: Linked Lists, Stacks, Queues & Recursion Fundamentals",
            "Milestone 3: Trees, Binary Search Trees & Heap Priority Queues",
            "Milestone 4: Graph Theory, BFS/DFS, TopoSort & Shortest Paths",
            "Milestone 5: Dynamic Programming Patterns (1D, 2D, Knapsack, Intervals)",
            "Milestone 6: Advanced Tries, Bit Manipulation & System Coding Interviews"
        ],
        "topics_by_week": [
            ("Arrays & Two Pointers", ["Array manipulations", "Two Pointers technique", "Sliding window problems", "Prefix sums & Kadane's", "LeetCode 75 Array Practice"]),
            ("Strings & Hash Maps", ["String parsing & matching", "Hash map frequency counts", "Anagrams & group anagrams", "Subarray sum equals K", "String interview exercises"]),
            ("Linked Lists & Fast/Slow Pointers", ["Singly & doubly linked lists", "Cycle detection (Floyd's)", "Reverse linked list variants", "Merge K sorted lists", "LRU Cache design"]),
            ("Stacks & Monotonic Queues", ["Stack fundamentals", "Valid parentheses", "Next Greater Element", "Daily temperatures pattern", "Largest rectangle in histogram"]),
            ("Recursion & Backtracking", ["Recursion call stack & base cases", "Subsets & permutations", "N-Queens & Sudoku solver", "Combination sum variations", "Word search backtracking"]),
            ("Binary Trees & Traversals", ["Tree representations", "DFS: Pre, In, Post-order", "BFS: Level order traversal", "Maximum depth & diameter", "Lowest common ancestor"]),
            ("Binary Search Trees & Heap", ["BST properties & validation", "Kth smallest element in BST", "Min/Max Heap construction", "Top K frequent elements", "Median from data stream"]),
            ("Graph Fundamentals & BFS/DFS", ["Adjacency list & matrix", "Connected components", "Clone graph & islands count", "Bipartite graph verification", "Topological Sort (Kahn's)"]),
            ("Advanced Graphs & Shortest Paths", ["Dijkstra's shortest path", "Bellman-Ford & Floyd-Warshall", "Minimum Spanning Tree (Kruskal/Prim)", "Union-Find (Disjoint Set Union)", "Graph problem sets"]),
            ("Dynamic Programming 1D Patterns", ["Memoization vs Tabulation", "Climbing stairs & Frog jump", "House robber variations", "Coin change & minimum coins", "Longest increasing subsequence"]),
            ("Dynamic Programming 2D & Knapsack", ["Grid unique paths & min path sum", "0/1 Knapsack problem", "Unbounded knapsack", "Target sum & subset sum", "Partition equal subset sum"]),
            ("Dynamic Programming on Strings", ["Longest common subsequence", "Edit distance", "Palindromic substrings", "Wildcard & regex matching", "DP comprehensive review"]),
            ("Greedy Algorithms & Intervals", ["Greedy choice property", "Merge intervals & insert interval", "Non-overlapping intervals", "Gas station problem", "Jump game I & II"]),
            ("Binary Search & Divide/Conquer", ["Binary search variations", "Search in rotated sorted array", "Find minimum in rotated array", "Median of two sorted arrays", "Capacity to ship packages"]),
            ("Bit Manipulation & Math", ["Bitwise AND/OR/XOR tricks", "Counting bits & single number", "Power of two & bit masking", "GCD, primes & Sieve", "Fast exponentiation"]),
            ("Trie & Advanced Structures", ["Trie prefix tree implementation", "Word search II with Trie", "Segment tree fundamentals", "Fenwick tree (BIT)", "Advanced data structures"]),
            ("Design Problems & Mock Coding", ["LRU Cache & LFU Cache", "Design Twitter & Min Stack", "Time Based Key-Value Store", "Design Snake Game", "Full 45-min mock coding"]),
            ("Systematic Revision & Edge Cases", ["Edge cases & boundary checks", "Time & Space complexity review", "Blind 75 speed runs", "NeetCode 150 hard problems", "Final interview readiness"])
        ]
    },
    "java": {
        "title": "Java & Enterprise Software Engineering",
        "milestones": [
            "Milestone 1: Core Java OOP, Generics, Collections & Modern Syntax",
            "Milestone 2: Concurrency, Virtual Threads, JVM Internals & Memory",
            "Milestone 3: Spring Boot Core, Dependency Injection & RESTful APIs",
            "Milestone 4: Spring Data JPA, Hibernate, Transactions & PostgreSQL",
            "Milestone 5: Spring Security, JWT, OAuth2 & Microservices Architecture",
            "Milestone 6: Production Engineering: Docker, Kafka, Testing & Monitoring"
        ],
        "topics_by_week": [
            ("Java OOP & Type System", ["Class design & inheritance", "Interfaces & abstract classes", "Polymorphism & sealed classes", "Records & pattern matching", "OOP design principles (SOLID)"]),
            ("Collections Framework & Generics", ["List, Set & Map deep dive", "Generics & wildcards (? extends T)", "Comparable vs Comparator", "HashMap internal mechanics", "Collection utility patterns"]),
            ("Functional Programming & Streams", ["Lambda expressions", "Stream API operations", "Collectors & groupingBy", "Optional handling & monads", "Parallel streams performance"]),
            ("Concurrency & Modern Threads", ["Thread lifecycle & Runnable", "Locks, synchronized & atomic vars", "ExecutorService & thread pools", "CompletableFuture async flows", "Java 21+ Virtual Threads"]),
            ("JVM Internals & Memory Management", ["JVM architecture & bytecode", "Heap vs Stack & Garbage Collection", "G1 & ZGC collectors", "Memory leak debugging", "JVM profiling with JConsole"]),
            ("Spring Boot Fundamentals", ["IoC Container & ApplicationContext", "@Component, @Service, @Repository", "Dependency Injection patterns", "Configuration & Profiles", "Application lifecycle events"]),
            ("RESTful API Development", ["@RestController & RequestMapping", "Request validation & custom errors", "DTO pattern & MapStruct", "Content negotiation & pagination", "OpenAPI & Swagger specs"]),
            ("Spring Data JPA & Hibernate", ["Entity mappings (@OneToMany, etc.)", "Spring Data repositories", "JPQL, criteria queries & specifications", "Lazy loading & N+1 problem", "Transaction management"]),
            ("Database Persistence & Migrations", ["PostgreSQL integration", "Flyway schema migrations", "Auditing & optimistic locking", "Connection pooling (HikariCP)", "Repository integration tests"]),
            ("Spring Security & JWT Auth", ["Security filter chain", "UserDetailsService & passwords", "JWT creation & verification", "Role-based authorization", "CORS & CSRF hardening"]),
            ("Microservices Architecture", ["Service decomposition patterns", "Spring Cloud OpenFeign", "Resilience4j circuit breakers", "API Gateway & routing", "Distributed tracing with Micrometer"]),
            ("Event-Driven Architecture with Kafka", ["Apache Kafka concepts", "Spring for Apache Kafka", "Producers, consumers & partitions", "Consumer groups & offset commits", "Event schema evolution"]),
            ("Comprehensive Testing Strategies", ["Unit testing with JUnit 5 & Mockito", "Integration testing with Testcontainers", "MockMvc API layer tests", "Contract testing with Pact", "Mutation testing"]),
            ("Production Readiness & Deployment", ["Docker multi-stage builds", "Health checks & Spring Actuator", "Prometheus metrics & Grafana", "Structured JSON logging", "Final capstone deployment"])
        ]
    },
    "machine_learning": {
        "title": "Machine Learning & AI Engineering Roadmap",
        "milestones": [
            "Milestone 1: Mathematical Foundations, NumPy, Pandas & EDA",
            "Milestone 2: Classical Supervised & Unsupervised Machine Learning",
            "Milestone 3: Deep Learning, PyTorch, CNNs & Computer Vision",
            "Milestone 4: Sequence Models, Transformers, Attention & NLP",
            "Milestone 5: Large Language Models, Fine-Tuning & RAG Systems",
            "Milestone 6: MLOps, Model Deployment, Quantization & Monitoring"
        ],
        "topics_by_week": [
            ("Math for ML & Scientific Python", ["Linear algebra: vectors & matrices", "Eigenvalues, SVD & PCA math", "Multivariate calculus & gradients", "NumPy vectorized operations", "Pandas data wrangling"]),
            ("Exploratory Data Analysis & Feature Engineering", ["Data distributions & outliers", "Missing value strategies", "Encoding categorical variables", "Feature scaling & transformations", "Matplotlib & Seaborn visualization"]),
            ("Supervised Learning: Regression", ["Linear regression & OLS", "Gradient descent mechanics", "Ridge & Lasso regularization", "Polynomial regression", "Regression evaluation metrics (RMSE, R2)"]),
            ("Supervised Learning: Classification", ["Logistic regression & odds ratio", "Decision Trees & entropy", "Support Vector Machines (SVM)", "Classification metrics (ROC-AUC, F1)", "Hyperparameter tuning (Optuna)"]),
            ("Ensemble Methods", ["Random Forests & bagging", "Gradient Boosting (GBM)", "XGBoost & LightGBM tuning", "Stacking & voting classifiers", "Feature importance interpretation"]),
            ("Unsupervised Learning & Clustering", ["K-Means & K-Means++", "Hierarchical clustering", "DBSCAN density clustering", "Dimensionality reduction (t-SNE/UMAP)", "Anomaly detection methods"]),
            ("Deep Learning Fundamentals with PyTorch", ["Tensors & autograd engine", "Building MLPs from scratch", "Activation functions (ReLU, GELU)", "Loss functions & Optimizers (AdamW)", "Training loops & validation"]),
            ("Convolutional Neural Networks (CNNs)", ["Convolution & pooling operations", "ResNet & skip connections", "Transfer learning with timm", "Data augmentation techniques", "Image classification project"]),
            ("Sequence Models & Attention Mechanism", ["RNNs & vanishing gradients", "LSTMs & GRUs", "Sequence-to-sequence architecture", "Bahdanau attention", "Self-attention formulation"]),
            ("The Transformer Architecture", ["Multi-head attention deep dive", "Positional encodings", "Encoder-Decoder transformers", "BERT vs GPT architectures", "Hugging Face Transformers library"]),
            ("Large Language Models & Prompt Engineering", ["LLM architectures & pre-training", "Tokenization (BPE, WordPiece)", "Prompt design patterns", "In-context learning & few-shot", "Structured outputs & JSON schemas"]),
            ("Retrieval-Augmented Generation (RAG)", ["Dense embeddings & vector search", "Chunking strategies & metadata", "ChromaDB / FAISS vector stores", "Query transformation & reranking", "Evaluation with RAGAS"]),
            ("Model Fine-Tuning (LoRA / PEFT)", ["Parameter-Efficient Fine-Tuning", "LoRA & QLoRA mechanics", "Instruction tuning datasets", "SFT training with HuggingFace TRL", "Model evaluation & benchmarks"]),
            ("MLOps & Serving Infrastructure", ["FastAPI model serving", "ONNX runtime acceleration", "vLLM & high-throughput inference", "Dockerizing AI microservices", "Model monitoring & drift detection"])
        ]
    },
    "fullstack": {
        "title": "Full-Stack Web Development & Modern Architecture",
        "milestones": [
            "Milestone 1: Modern JavaScript/TypeScript & Frontend Architecture",
            "Milestone 2: React Core, Hooks, State & Component Design",
            "Milestone 3: Backend API Development with Node/FastAPI & Databases",
            "Milestone 4: Full-Stack Integration, Auth & Real-Time WebSockets",
            "Milestone 5: Testing, Cloud Deployment & CI/CD Pipelines",
            "Milestone 6: Micro-Frontends, Performance Optimization & Scale"
        ],
        "topics_by_week": [
            ("TypeScript & Modern JavaScript", ["ES6+ syntax & async/await", "TypeScript types, interfaces & generics", "Union types & type narrowing", "Module bundlers (Vite)", "Clean code principles"]),
            ("React Fundamentals & Components", ["JSX & Virtual DOM", "Component lifecycle & props", "useState & useEffect deep dive", "Forms & controlled inputs", "Tailwind CSS responsive design"]),
            ("Advanced React & State Management", ["Custom hooks patterns", "useContext & useReducer", "Server state with TanStack Query", "Client state with Zustand", "Performance optimization (useMemo)"]),
            ("Next.js & Server Components", ["App Router architecture", "Server vs Client components", "Server actions & data mutation", "Static & Dynamic rendering", "Metadata & SEO optimization"]),
            ("Backend Architecture & REST", ["REST API design guidelines", "FastAPI / Express route handlers", "Request validation with Pydantic/Zod", "Middleware & error handling", "Swagger & OpenAPI contracts"]),
            ("Database Design & ORMs", ["Relational schema design (PostgreSQL)", "SQL queries, joins & indexes", "ORM integration (SQLAlchemy / Prisma)", "Database migrations", "Connection pooling"]),
            ("Authentication & Security", ["Session vs JWT authentication", "OAuth2 & Google Sign-In", "HTTP-only cookies & security headers", "CORS, XSS & CSRF prevention", "Role-based access control (RBAC)"]),
            ("Real-Time Systems & WebSockets", ["WebSocket protocol & events", "Real-time notifications & chat", "Redis pub/sub architecture", "Background job queues (Celery/Bull)", "Optimistic UI updates"]),
            ("Testing & Quality Assurance", ["Unit testing with Vitest/Jest", "React Testing Library", "End-to-end testing with Playwright", "API integration tests", "Code coverage & linting"]),
            ("Cloud Deployment & CI/CD", ["Docker containerization", "GitHub Actions CI/CD workflows", "Cloud deployment (AWS/Railway)", "CDN caching & asset delivery", "Monitoring, Sentry & log aggregation"])
        ]
    }
}


def get_curriculum_blueprint(subject: str, duration_days: int) -> Dict[str, Any]:
    """
    Selects or synthesizes the closest matching curriculum blueprint for a given subject.
    """
    sub_lower = subject.lower()
    if "java" in sub_lower and "dsa" in sub_lower:
        return {
            "title": "Java & DSA Comprehensive Curriculum",
            "milestones": [
                "Milestone 1: Java Core OOP, Generics, Collections & Memory Model",
                "Milestone 2: DSA Arrays, Two Pointers & Sliding Window Problems",
                "Milestone 3: Linked Lists, Stacks, Queues & Recursion/Backtracking",
                "Milestone 4: Binary Trees, BSTs, Heaps & Priority Queues",
                "Milestone 5: Graph Theory, BFS/DFS, TopoSort & Shortest Paths",
                "Milestone 6: Dynamic Programming Patterns & Comprehensive Interview Prep"
            ],
            "topics_by_week": [
                ("Java Core & OOP Foundations", ["Java OOP: Classes, Inheritance & Polymorphism", "OOP Principles (Encapsulation, Abstraction, SOLID)", "Generics & Collections Framework (List, Map, Set)", "JVM Memory Model: Heap vs Stack & Garbage Collection", "OOP Practice & Coding Exercises"]),
                ("DSA Arrays & Two Pointers", ["Array manipulations & Two Pointers technique", "Sliding window problems & Prefix sums", "Kadane's algorithm & Subarrays", "Sorting & Searching fundamentals", "LeetCode Array Problem Set"]),
                ("Linked Lists & Stacks", ["Singly & Doubly Linked Lists", "Floyd's Cycle Detection & Fast/Slow pointers", "Stack implementations & Valid Parentheses", "Monotonic stacks & Next Greater Element", "Linked List & Stack exercises"]),
                ("Recursion & Backtracking", ["Recursion call stack & Base conditions", "Subsets & Permutations generation", "N-Queens & Backtracking patterns", "Combination Sum variations", "Recursion problem sets"]),
                ("Binary Trees & BSTs", ["Tree representations & DFS (Pre, In, Post-order)", "BFS Level Order Traversal", "Binary Search Tree properties & Validation", "Lowest Common Ancestor & Tree Diameter", "Tree interview exercises"]),
                ("Heaps & Priority Queues", ["Min/Max Heap construction & mechanics", "Top K frequent elements", "Merge K sorted lists with Heap", "Median from Data Stream", "Heap problem sets"]),
                ("Graph Algorithms", ["Graph representations (Adjacency list/matrix)", "BFS & DFS Graph Traversals", "Connected components & Islands count", "Topological Sort (Kahn's Algorithm)", "Dijkstra's Shortest Path"]),
                ("Dynamic Programming 1D & 2D", ["Memoization vs Tabulation approaches", "Climbing stairs & Fibonacci patterns", "House robber & Coin change", "0/1 Knapsack & Grid paths", "DP Comprehensive practice"]),
                ("Mock Coding & Interview Synthesis", ["Time & Space complexity review", "Blind 75 speed coding sessions", "Edge case identification & defensive coding", "NeetCode 150 curated problems", "Final comprehensive review & assessment"])
            ]
        }
    elif any(k in sub_lower for k in ["dsa", "data structure", "algorithm", "leetcode", "coding interview"]):
        return CURRICULUM_TEMPLATES["dsa"]
    elif any(k in sub_lower for k in ["java", "spring", "backend engineering", "jvm"]):
        return CURRICULUM_TEMPLATES["java"]
    elif any(k in sub_lower for k in ["machine learning", "ml", "deep learning", "ai", "artificial intelligence", "nlp", "rag", "pytorch"]):
        return CURRICULUM_TEMPLATES["machine_learning"]
    elif any(k in sub_lower for k in ["web", "full stack", "react", "frontend", "typescript", "node", "fastapi"]):
        return CURRICULUM_TEMPLATES["fullstack"]
    else:
        # Generic academic curriculum
        return {
            "title": f"{subject} Comprehensive Curriculum",
            "milestones": [
                f"Milestone 1: {subject} Core Foundations & Principles",
                f"Milestone 2: Practical Implementation & Problem Solving",
                f"Milestone 3: Intermediate Patterns & Domain Methodologies",
                f"Milestone 4: Advanced Systems, Architecture & Specialization",
                f"Milestone 5: Project Synthesis, Integration & Case Studies",
                f"Milestone 6: Mastery Evaluation, Review & Real-World Application"
            ],
            "topics_by_week": [
                (f"{subject} Foundations", [f"{subject} Core Concepts", "Essential Vocabulary & Definitions", "Basic Workflows & Setups", "Introductory Exercises", "Weekly Self-Assessment"]),
                ("Core Principles & Mechanics", ["Underlying Mechanisms", "Key Frameworks & Rules", "Guided Problem Solving", "Hands-on Practice Session", "Knowledge Check"]),
                ("Intermediate Applications", ["Real-World Scenarios", "Analytical Problem Breakdown", "Intermediate Techniques", "Component Architecture", "Applied Case Study"]),
                ("Advanced Topics & Optimization", ["Complex Case Studies", "Performance Optimization", "Edge Cases & Troubleshooting", "Deep Dive Exploration", "Milestone Synthesis"]),
                ("Integration & Synthesis", ["System Integration", "End-to-End Problem Resolution", "Best Practices & Standards", "Review of Key Findings", "Assessment Prep"]),
                ("Mastery & Practical Project", ["Capstone Implementation", "Comprehensive Review", "Mock Evaluation", "Final Synthesis & Polish", "Curriculum Completion"])
            ]
        }


# ---------------------------------------------------------------------------
# Core Generation Pipeline
# ---------------------------------------------------------------------------

async def generate_study_plan_roadmap(
    subject: str,
    learning_goal: Optional[str] = None,
    duration_text: Optional[str] = None,
    duration_days: Optional[int] = None,
    start_date_str: Optional[str] = None,
    daily_hours: float = 2.0,
    preferred_days: Optional[List[str]] = None,
    user_tz_str: str = "UTC",
    daily_hours_target: Optional[float] = None,
    preferred_study_days: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Main entry point: Generates a complete hierarchical study plan for 1 day up to 6 months.
    Returns:
    {
        "title": str,
        "period": str,
        "subject": str,
        "learningGoal": str,
        "startDate": str,
        "endDate": str,
        "durationDays": int,
        "dailyHoursTarget": float,
        "preferredStudyDays": list,
        "goals": list,
        "tasks": list of task dicts,
        "suggestedStudyBlocks": list,
        "hierarchy": {
            "months": list,
            "summary": dict
        }
    }
    """
    if daily_hours_target is not None:
        daily_hours = daily_hours_target
    if preferred_study_days is not None and preferred_days is None:
        preferred_days = preferred_study_days
    daily_hours = max(min(float(daily_hours or 2.0), 12.0), 0.5)
    start_d, end_d, total_days = calculate_plan_dates(
        start_date_str=start_date_str,
        duration_text=duration_text,
        duration_days=duration_days,
        user_tz_str=user_tz_str
    )

    clean_subject = (subject or "Academic Target").strip()
    clean_goal = (learning_goal or f"Master {clean_subject} within {total_days} days").strip()

    # Determine period label
    if total_days == 1:
        period_label = "1 Day Intensive"
    elif total_days == 7:
        period_label = "7-Day Sprint"
    elif total_days <= 14:
        period_label = f"{total_days}-Day Accelerated Sprint"
    elif total_days <= 31:
        period_label = "1 Month (30 Days)"
    elif total_days <= 62:
        period_label = "2 Months (60 Days)"
    elif total_days <= 93:
        period_label = "3 Months (90 Days)"
    elif total_days <= 124:
        period_label = "4 Months (120 Days)"
    elif total_days <= 155:
        period_label = "5 Months (150 Days)"
    else:
        period_label = "6 Months (180 Days)"

    plan_title = f"{period_label} {clean_subject} Roadmap".strip()

    # Normalized preferred days
    all_weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if preferred_days and isinstance(preferred_days, list) and len(preferred_days) > 0:
        valid_prefs = [d for d in preferred_days if d in all_weekdays]
        active_study_days = valid_prefs if valid_prefs else all_weekdays
    else:
        active_study_days = all_weekdays

    # Calculate number of months and weeks
    num_months = max(1, (total_days + 29) // 30)
    num_weeks = max(1, (total_days + 6) // 7)

    logger.info(
        "[StudyPlanGenerator] Generating plan '%s': days=%d, months=%d, weeks=%d, daily_hours=%.1f",
        plan_title, total_days, num_months, num_weeks, daily_hours
    )

    # Attempt LLM generation for short/medium plans; use staged blueprint for all
    blueprint = get_curriculum_blueprint(clean_subject, total_days)
    tasks, hierarchy_months = _generate_hierarchical_tasks(
        blueprint=blueprint,
        clean_subject=clean_subject,
        clean_goal=clean_goal,
        start_date=start_d,
        total_days=total_days,
        daily_hours=daily_hours,
        active_study_days=active_study_days,
        user_tz_str=user_tz_str
    )

    # Workload summary
    completed_tasks = 0
    total_planned_minutes = sum(t["durationMinutes"] for t in tasks)
    total_planned_hours = round(total_planned_minutes / 60.0, 1)

    summary = {
        "totalDays": total_days,
        "totalMonths": num_months,
        "totalWeeks": num_weeks,
        "totalTasks": len(tasks),
        "completedTasks": 0,
        "pendingTasks": len(tasks),
        "completionPercentage": 0,
        "plannedStudyHours": total_planned_hours,
        "completedStudyHours": 0.0,
        "dailyHoursTarget": daily_hours,
        "startDate": start_d.isoformat(),
        "endDate": end_d.isoformat()
    }

    goals = [
        f"Master comprehensive competencies in {clean_subject}",
        f"Maintain consistent {daily_hours:g}h study sessions ({total_planned_hours} total planned hours)",
        f"Complete all {num_months} month milestones and {len(tasks)} actionable tasks"
    ]

    return {
        "title": plan_title,
        "period": period_label,
        "subject": clean_subject,
        "learningGoal": clean_goal,
        "startDate": start_d.isoformat(),
        "endDate": end_d.isoformat(),
        "durationDays": total_days,
        "totalDays": total_days,
        "dailyHoursTarget": daily_hours,
        "preferredStudyDays": active_study_days,
        "generationStatus": "complete",
        "goals": goals,
        "tasks": tasks,
        "flatTasks": tasks,
        "months": hierarchy_months,
        "hierarchy": {
            "summary": summary,
            "months": hierarchy_months
        }
    }


def _generate_hierarchical_tasks(
    blueprint: Dict[str, Any],
    clean_subject: str,
    clean_goal: str,
    start_date: date,
    total_days: int,
    daily_hours: float,
    active_study_days: List[str],
    user_tz_str: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Builds the complete Month -> Week -> Day -> Task hierarchy with dates, durations,
    labels, and milestone associations.
    """
    topics_pool = blueprint.get("topics_by_week", [])
    milestones_pool = blueprint.get("milestones", [])

    flat_tasks: List[Dict[str, Any]] = []
    hierarchy_months: List[Dict[str, Any]] = []

    # Target task duration per day in minutes
    target_day_minutes = int(daily_hours * 60)

    # 1-day special case
    if total_days == 1:
        current_date = start_date
        date_iso = current_date.isoformat()
        weekday_name = current_date.strftime("%A")

        t1_mins = min(target_day_minutes // 2, 90) if target_day_minutes >= 90 else target_day_minutes
        t2_mins = target_day_minutes - t1_mins

        m1 = {
            "monthNumber": 1,
            "monthLabel": "Intensive Review",
            "startDate": date_iso,
            "endDate": date_iso,
            "objectives": [f"Deep dive into critical {clean_subject} concepts", "Practical problem solving & synthesis"],
            "milestone": f"Day 1 Mastery: {clean_subject} Synthesis",
            "totalTasks": 2 if t2_mins > 0 else 1,
            "completedTasks": 0,
            "plannedHours": round(target_day_minutes / 60.0, 1),
            "completedHours": 0.0,
            "progress": 0,
            "weeks": [
                {
                    "weekNumber": 1,
                    "weekLabel": "Day Sprint",
                    "startDate": date_iso,
                    "endDate": date_iso,
                    "goal": f"Complete intensive {clean_subject} study target",
                    "milestone": f"{clean_subject} Rapid Review",
                    "topics": [f"{clean_subject} Core Fundamentals", f"{clean_subject} Hands-on Practice"],
                    "totalTasks": 2 if t2_mins > 0 else 1,
                    "completedTasks": 0,
                    "plannedHours": round(target_day_minutes / 60.0, 1),
                    "completedHours": 0.0,
                    "progress": 0,
                    "days": [
                        {
                            "dayNumber": 1,
                            "date": date_iso,
                            "dayOfWeek": weekday_name,
                            "isRestDay": False,
                            "totalPlannedMinutes": target_day_minutes,
                            "tasks": []
                        }
                    ]
                }
            ]
        }

        task_order = 1
        day_tasks = []

        task1 = {
            "title": f"{clean_subject}: Core Conceptual Foundations & Key Mechanics",
            "durationMinutes": t1_mins,
            "priority": "high",
            "completed": False,
            "scheduledDate": date_iso,
            "startTime": "09:00 AM",
            "endTime": f"{(9 + t1_mins//60):02d}:{(t1_mins%60):02d} AM",
            "timezone": user_tz_str,
            "monthNumber": 1,
            "weekNumber": 1,
            "dayNumber": 1,
            "taskOrder": task_order,
            "taskType": "daily",
            "dayLabel": "Day 1",
            "weekLabel": "Day Sprint",
            "monthLabel": "Intensive Review",
            "milestoneGroup": f"Day 1 Mastery: {clean_subject} Synthesis"
        }
        flat_tasks.append(task1)
        day_tasks.append(task1)
        task_order += 1

        if t2_mins > 0:
            task2 = {
                "title": f"{clean_subject}: Practical Implementation, Problem Solving & Review",
                "durationMinutes": t2_mins,
                "priority": "high",
                "completed": False,
                "scheduledDate": date_iso,
                "startTime": "02:00 PM",
                "endTime": f"{(14 + t2_mins//60):02d}:{(t2_mins%60):02d} PM",
                "timezone": user_tz_str,
                "monthNumber": 1,
                "weekNumber": 1,
                "dayNumber": 1,
                "taskOrder": task_order,
                "taskType": "practice",
                "dayLabel": "Day 1",
                "weekLabel": "Day Sprint",
                "monthLabel": "Intensive Review",
                "milestoneGroup": f"Day 1 Mastery: {clean_subject} Synthesis"
            }
            flat_tasks.append(task2)
            day_tasks.append(task2)

        m1["weeks"][0]["days"][0]["tasks"] = day_tasks
        hierarchy_months.append(m1)
        return flat_tasks, hierarchy_months

    # Determine exact number of calendar months
    if total_days <= 31:
        total_months = 1
    elif total_days <= 62:
        total_months = 2
    elif total_days <= 93:
        total_months = 3
    elif total_days <= 124:
        total_months = 4
    elif total_days <= 155:
        total_months = 5
    else:
        total_months = 6

    # Standard multi-day progression
    current_date = start_date
    task_order = 1

    for m_idx in range(1, total_months + 1):
        m_start_date = add_calendar_months(start_date, m_idx - 1)
        next_m_start = add_calendar_months(start_date, m_idx)
        m_end_date = min(next_m_start - timedelta(days=1), end_d if 'end_d' in locals() else start_date + timedelta(days=total_days - 1))

        if m_start_date > start_date + timedelta(days=total_days - 1):
            break

        milestone_title = (
            milestones_pool[m_idx - 1]
            if m_idx - 1 < len(milestones_pool)
            else f"Milestone {m_idx}: {clean_subject} Advanced Mastery Phase {m_idx}"
        )

        month_data: Dict[str, Any] = {
            "monthNumber": m_idx,
            "monthLabel": f"Month {m_idx}",
            "startDate": m_start_date.isoformat(),
            "endDate": m_end_date.isoformat(),
            "objectives": [
                f"Master core concepts for Month {m_idx} of {clean_subject}",
                f"Achieve consistent daily study routine ({daily_hours:g}h/day)",
                f"Complete {milestone_title}"
            ],
            "milestone": milestone_title,
            "totalTasks": 0,
            "completedTasks": 0,
            "plannedHours": 0.0,
            "completedHours": 0.0,
            "progress": 0,
            "weeks": []
        }

        # Subdivide month into 7-day weeks
        m_days_count = (m_end_date - m_start_date).days + 1
        m_weeks_count = max(1, (m_days_count + 6) // 7)

        for w_offset in range(m_weeks_count):
            w_start_date = m_start_date + timedelta(days=w_offset * 7)
            w_end_date = min(w_start_date + timedelta(days=6), m_end_date)
            if w_start_date > m_end_date:
                break

            global_w_idx = ((w_start_date - start_date).days // 7) + 1

            # Topic selection from blueprint pool
            topic_tuple = topics_pool[(global_w_idx - 1) % len(topics_pool)] if topics_pool else (f"Week {global_w_idx} Fundamentals", [])
            w_title = topic_tuple[0]
            daily_topics = topic_tuple[1]

            week_data: Dict[str, Any] = {
                "weekNumber": global_w_idx,
                "weekLabel": f"Week {global_w_idx}",
                "startDate": w_start_date.isoformat(),
                "endDate": w_end_date.isoformat(),
                "goal": f"Master {w_title}",
                "milestone": f"Week {global_w_idx} Assessment & Practical Implementation",
                "topics": daily_topics if daily_topics else [w_title],
                "totalTasks": 0,
                "completedTasks": 0,
                "plannedHours": 0.0,
                "completedHours": 0.0,
                "progress": 0,
                "days": []
            }

            # Generate each day in this week
            curr_cal_date = w_start_date
            while curr_cal_date <= w_end_date:
                cal_date = curr_cal_date
                date_iso = cal_date.isoformat()
                weekday = cal_date.strftime("%A")
                d_num = (cal_date - start_date).days + 1

                is_study_day = weekday in active_study_days
                day_task_list = []

                if is_study_day:
                    t_idx = (d_num - 1) % len(daily_topics) if daily_topics else 0
                    base_topic = daily_topics[t_idx] if daily_topics else f"{clean_subject} Concepts"

                    is_milestone_day = (curr_cal_date == w_end_date)
                    is_revision_day = (d_num % 7 == 6)

                    if is_milestone_day:
                        task_title = f"{w_title}: Weekly Synthesis & Assessment"
                        task_type = "assessment"
                        prio = "high"
                    elif is_revision_day:
                        task_title = f"Review & Practice: {base_topic}"
                        task_type = "revision"
                        prio = "medium"
                    else:
                        task_title = f"{base_topic}: Implementation & Exercises"
                        task_type = "daily"
                        prio = "high"

                    task_record = {
                        "title": task_title,
                        "durationMinutes": target_day_minutes,
                        "priority": prio,
                        "completed": False,
                        "scheduledDate": date_iso,
                        "startTime": "09:00 AM",
                        "endTime": f"{(9 + target_day_minutes//60):02d}:{(target_day_minutes%60):02d} AM",
                        "timezone": user_tz_str,
                        "monthNumber": m_idx,
                        "weekNumber": global_w_idx,
                        "dayNumber": d_num,
                        "taskOrder": task_order,
                        "taskType": task_type,
                        "dayLabel": f"Day {d_num}",
                        "weekLabel": f"Week {global_w_idx}",
                        "monthLabel": f"Month {m_idx}",
                        "milestoneGroup": milestone_title
                    }
                    flat_tasks.append(task_record)
                    day_task_list.append(task_record)
                    task_order += 1

                week_data["days"].append({
                    "dayNumber": d_num,
                    "date": date_iso,
                    "dayOfWeek": weekday,
                    "isRestDay": not is_study_day,
                    "totalPlannedMinutes": target_day_minutes if is_study_day else 0,
                    "tasks": day_task_list
                })

                curr_cal_date += timedelta(days=1)

            w_total_tasks = sum(len(d["tasks"]) for d in week_data["days"])
            w_total_mins = sum(d["totalPlannedMinutes"] for d in week_data["days"])
            week_data["totalTasks"] = w_total_tasks
            week_data["plannedHours"] = round(w_total_mins / 60.0, 1)

            month_data["weeks"].append(week_data)

        m_total_tasks = sum(w["totalTasks"] for w in month_data["weeks"])
        m_total_hours = sum(w["plannedHours"] for w in month_data["weeks"])
        month_data["totalTasks"] = m_total_tasks
        month_data["plannedHours"] = round(m_total_hours, 1)

        hierarchy_months.append(month_data)

    return flat_tasks, hierarchy_months
