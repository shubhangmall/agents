#!/usr/bin/env python
import sys
import warnings
import os
from datetime import datetime

from engineering_team.crew import EngineeringTeam

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# Create output directory if it doesn't exist
os.makedirs('output', exist_ok=True)

requirements = """
A simple research assistant agent for exploring and summarizing academic papers.
The system should allow users to create a research project and add topics or keywords of interest.
The system should allow the agent to fetch papers for each topic using a function get_papers(query),
    which returns metadata (title, authors, abstract, link).
The system should allow users to record notes on a paper and mark it as relevant or not.
The system should summarize the abstracts of fetched papers, and generate a comparison between multiple papers on the same topic.
The system should calculate and report the top 3 key insights from the collected papers in a project.
The system should be able to list all papers explored, along with user notes and relevance marks.
The system should be able to export a project summary including:
    - project topics
    - list of papers
    - notes
    - final insights
The system should prevent duplicate papers being added to a project.
The system has access to a function get_papers(query) which includes a test implementation that returns
    fixed example papers for queries like "AI", "quantum computing", and "climate change".
"""
module_name = "research_agent.py"
class_name = "ResearchAssistant"


def run():
    """
    Run the research crew.
    """
    inputs = {
        'requirements': requirements,
        'module_name': module_name,
        'class_name': class_name
    }

    # Create and run the crew
    result = EngineeringTeam().crew().kickoff(inputs=inputs)


if __name__ == "__main__":
    run()