# Prompt history

Prompts given to Claude Code (VS Code) while building this project, in order.

### 1. Problem Statement and Project Structure

**Prompt 01 – Problem Understanding and Initial Architecture**

The full project brief was provided: recommend next learning activities based on skills, prerequisites, assessment results, and content difficulty, including entities, ID conventions, synthetic data requirements, edge cases, and acceptance criteria.

The prompt ended with:

> "make me to help this project as in the structure of three tier frontend backend and database use the database synthetic."

The goal was to understand the business problem and establish a three-tier architecture using synthetic data.

### 2. Three-Tier Architecture and Folder Structure

**Prompt 02 – Enforce Frontend, Backend, and Database Separation**

> "no follow the three tier rule as frontend part inside the frontend and backend part inside backend and all database is present inside the database folder"

This was used to restructure the project so that:

- Frontend code remains inside the `frontend` folder.
- Backend/API code remains inside the `backend` folder.
- Database schema, synthetic data, SQL, and related database files remain inside the `database` folder.
- The project follows a clear three-tier separation.

The implementation also included the `generator` CLI package, schema-driven DDL and documentation, synthetic data organized under `data/<scale>/`, validation checks, checksums, reproducibility scripts, AI usage documentation, and a React + Vite + Tailwind frontend.

### 3. Architecture Compliance

**Prompt 03 – Confirm Three-Tier Rule**

> "make sure follow the three tier rule like frontend, backend and database"

This was used to verify that the implementation continued to follow the required separation between the frontend, backend, and database layers and that project files were placed in the appropriate layer.

### 4. Backend and API Implementation

**Prompt 04 – FastAPI Backend**

Set up the backend using FastAPI and connect it with the database layer. Define the required API structure and endpoints for the learning recommendation workflow.

The backend was designed to:

- Receive learner and learning-related requests.
- Process recommendation logic.
- Access synthetic database data.
- Return recommendation results to the frontend.
- Keep API and business logic separated from the React frontend.

### 5. Learning Recommendation Logic

**Prompt 05 – Recommendation Workflow**

Implement the recommendation workflow based on:

- Learner skills.
- Required and missing skills.
- Skill prerequisites.
- Assessment results.
- Content difficulty.
- Learning activity relationships.

The recommendation logic should determine suitable next learning activities while respecting prerequisites and learner readiness.

### 6. Business Rules and Edge Cases

**Prompt 06 – Handle Recommendation Exceptions**

Implement business rules and handle cases such as:

- Missing learner skills.
- Missing assessment results.
- Unmet prerequisites.
- Invalid or missing content difficulty.
- Duplicate learning activities.
- No suitable recommendation available.
- Incorrect or incomplete synthetic data.

Each exception should be handled predictably and should not cause the complete recommendation workflow to fail.

### 7. Synthetic Data and Database

**Prompt 07 – Synthetic Data Generation**

Generate realistic synthetic data for learners, skills, prerequisites, assessments, learning activities, difficulty levels, and recommendation-related records.

The generated data should maintain valid relationships between entities and be reproducible for testing.

### 8. Frontend Integration

**Prompt 08 – React Frontend and FastAPI Integration**

Connect the React frontend with the FastAPI backend and display the recommendation results through the dashboard.

The frontend should:

- Send requests to the FastAPI API.
- Receive recommendation responses.
- Display learner information and recommended learning activities.
- Handle API errors and empty recommendation results.
- Keep frontend code separate from backend implementation.

### 9. Testing and Validation

**Prompt 09 – Functional Testing**

Create test cases covering:

- Learner skill matching.
- Prerequisite validation.
- Assessment-based recommendations.
- Content difficulty handling.
- Recommendation ranking/selection.
- Missing and invalid data.
- API responses.
- Empty recommendation scenarios.
- Frontend-to-backend integration.

### 10. Code Review and Debugging

**Prompt 10 – Code Review and Debugging**

Review the existing code, identify errors, explain their causes, and suggest the smallest reliable fixes without changing unrelated functionality.

Debug issues related to:

- FastAPI endpoints.
- Database queries.
- Recommendation logic.
- Data validation.
- Frontend API integration.
- Incorrect or unexpected recommendation results.

### 11. Final Project Validation

**Prompt 11 – Final Project Validation**

Review the complete application against the original requirements.

Identify:

- Missing functionality.
- Test results.
- Incorrect business logic.
- API issues.
- Database consistency issues.
- Frontend integration issues.
- Areas that need improvement.

Verify that the final implementation satisfies the expected workflow and acceptance criteria.

### 12. Final Architecture and AI Validation

**Prompt 12 – Final Review of Project Structure**

Review the complete project structure and confirm that the application follows the required three-tier architecture:

- **Frontend:** React + Vite + Tailwind.
- **Backend:** Python + FastAPI.
- **Database:** Synthetic data, schema, SQL, and database-related files.

Also verify that responsibilities are separated correctly between the three layers and that the frontend communicates with the backend through the FastAPI API rather than directly accessing the database.

### 13. Development Approach

- Used AI to understand the business problem, requirements, architecture, and technical implementation.
- Used AI to plan the three-tier project structure.
- Used AI assistance for implementing the FastAPI backend and recommendation workflow.
- Used AI assistance for synthetic data generation and database-related implementation.
- Used AI assistance for React frontend development and frontend-backend integration.
- Ran and tested AI-generated code before using it.
- Kept frontend, backend, business logic, and database responsibilities separated.
- Focused on accurate recommendation logic and proper exception handling.
- Maintained data consistency between learners, skills, prerequisites, assessments, and learning activities.
- Tested the application against the expected requirements and acceptance criteria.

### 14. Important Note

AI was used extensively during development for backend code, recommendation logic, tests, documentation, database-related code, and the React dashboard.

I provided the requirements and development direction, reviewed the generated implementation, ran and tested the code on my own machine, debugged issues, and verified the final results before using them in the project.

The AI-assisted development process and usage are documented separately in `AI_USAGE.md`.

### 15. Why FastAPI Is Used

FastAPI is used in this project because the application follows a three-tier frontend-backend-database architecture.

The FastAPI backend acts as the API layer between the React frontend and the database.

- The React frontend sends requests to FastAPI.
- FastAPI validates and processes incoming requests.
- The backend executes the recommendation/business logic.
- FastAPI communicates with the database and retrieves the required learner, skill, assessment, prerequisite, and learning-activity data.
- The API returns structured recommendation results to the React frontend.
- Keeping the API layer separate prevents the frontend from directly accessing the database.
- FastAPI also provides automatic API documentation through Swagger/OpenAPI, which helps with development and testing.

The three-tier flow is:

**React Frontend → FastAPI Backend → Database**

This structure keeps the presentation layer, application/business logic, and data layer separated and makes the project easier to test, maintain, and extend.

FastAPI also provides a foundation for future functionality such as authentication, user-specific recommendations, saving learner progress, recommendation history, and integration with an AI/ML recommendation model.