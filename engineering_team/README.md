# EngineeringTeam Crew

Welcome to the EngineeringTeam Crew project, powered by [crewAI](https://crewai.com).

## Installation

Ensure you have Python >=3.10 <3.13 installed on the system. This project uses [UV](https://docs.astral.sh/uv/) for dependency management and package handling, offering a seamless setup and execution experience.

First, if you haven't already, install uv:

```bash
pip install uv
```

Next, navigate to the project directory and install the dependencies:

(Optional) Lock the dependencies and install them by using the CLI command:

```bash
crewai install
```

### Customizing

**Add the `OPENAI_API_KEY` into the `.env` file**

- Modify `src/engineering_team/config/agents.yaml` to define the agents
- Modify `src/engineering_team/config/tasks.yaml` to define the tasks
- Modify `src/engineering_team/crew.py` to add the own logic, tools and specific args
- Modify `src/engineering_team/main.py` to add custom inputs for the agents and tasks

## Running the Project

To kickstart the crew of AI agents and begin task execution, run this from the root folder of the project:

```bash
$ crewai run
```

This command initializes the engineering_team Crew, assembling the agents and assigning them tasks as defined in the configuration.

This example, unmodified, will run the create a `accounts.py` and `app.py` file with the output of the application created by AI agents in the root folder.
