# research_agent.py

class ResearchAssistant:
    def __init__(self, project_name: str):
        """
        Initializes a new research project with the given project name.
        
        Args:
            project_name (str): The name of the research project.
        """
        self.project_name = project_name
        self.topics = []
        self.papers = {}
        self.notes = {}
        self.relevance = {}
    
    def add_topic(self, topic: str) -> None:
        """
        Adds a topic/keyword of interest to the research project.
        
        Args:
            topic (str): The topic or keyword to be added.
        """
        if topic not in self.topics:
            self.topics.append(topic)
    
    def get_papers(self, query: str) -> list:
        """
        Fetches academic papers based on the given query.
        
        Args:
            query (str): A topic or keyword to search for papers.
        
        Returns:
            list: A list of paper metadata dictionaries, each containing
                  'title', 'authors', 'abstract', and 'link'.
        """
        # The actual implementation calls the external get_papers function
        return get_papers(query)
    
    def add_papers(self, query: str) -> None:
        """
        Adds papers fetched by the agent for a given topic, 
        preventing duplicates from being added to the project.
        
        Args:
            query (str): A topic or keyword to fetch papers for.
        """
        fetched_papers = self.get_papers(query)
        for paper in fetched_papers:
            if paper['link'] not in self.papers:
                self.papers[paper['link']] = paper
                self.notes[paper['link']] = ""
                self.relevance[paper['link']] = None
    
    def record_notes(self, paper_link: str, note: str) -> None:
        """
        Records user notes on a specific paper.
        
        Args:
            paper_link (str): The link of the paper to record notes on.
            note (str): The note to be recorded.
        """
        if paper_link in self.notes:
            self.notes[paper_link] = note
    
    def mark_relevance(self, paper_link: str, relevance: bool) -> None:
        """
        Marks a paper as relevant or not relevant.
        
        Args:
            paper_link (str): The link of the paper.
            relevance (bool): True if relevant, False otherwise.
        """
        if paper_link in self.relevance:
            self.relevance[paper_link] = relevance
    
    def summarize_abstracts(self) -> dict:
        """
        Summarizes the abstracts of all fetched papers.
        
        Returns:
            dict: A dictionary mapping paper links to their abstract summaries.
        """
        summaries = {}
        for link, paper in self.papers.items():
            # In a real implementation, this would use an NLP model to summarize
            # For now, we'll just use the abstracts as their own summaries
            summaries[link] = f"Summary of '{paper['title']}': {paper['abstract']}"
        return summaries
    
    def compare_papers(self, topic: str) -> dict:
        """
        Generates a comparison of multiple papers on the same topic.
        
        Args:
            topic (str): The topic for comparison.
        
        Returns:
            dict: A comparison summary of the papers associated with the topic.
        """
        # First fetch papers for this topic if not already done
        if topic not in self.topics:
            return {"error": f"Topic '{topic}' not in project topics. Add it first."}
            
        # Ensure we have papers for this topic
        papers_on_topic = []
        for link, paper in self.papers.items():
            # Simple matching - in a real implementation, this would be more sophisticated
            if topic.lower() in paper['title'].lower() or topic.lower() in paper['abstract'].lower():
                papers_on_topic.append(paper)
        
        if not papers_on_topic:
            return {"message": f"No papers found on topic '{topic}'"}
        
        # Create comparison
        comparison = {
            "topic": topic,
            "paper_count": len(papers_on_topic),
            "papers": {},
            "common_themes": f"Papers on {topic} explore various aspects of the field.",
            "differences": f"Papers show different approaches to {topic}."
        }
        
        for paper in papers_on_topic:
            comparison["papers"][paper['link']] = {
                'title': paper['title'],
                'authors': paper['authors'],
                'abstract_summary': paper['abstract'][:100] + "..."
            }
            
        return comparison
    
    def calculate_insights(self) -> list:
        """
        Calculates and reports top 3 key insights from collected papers.
        
        Returns:
            list: A list of top 3 insights.
        """
        # In a real implementation, this would use NLP to extract key insights
        # For the mock implementation, we'll generate simple insights based on available papers
        
        insights = []
        relevant_papers = [paper for link, paper in self.papers.items() 
                         if self.relevance.get(link) is True]
        
        if not relevant_papers:
            # Fall back to all papers if none are marked relevant
            relevant_papers = list(self.papers.values())
        
        # Generate insights based on papers
        if relevant_papers:
            # Generate up to 3 insights
            count = min(3, len(relevant_papers))
            for i in range(count):
                paper = relevant_papers[i]
                insights.append(f"Insight from '{paper['title']}': "
                               f"This paper by {paper['authors']} suggests that {paper['abstract'][:50]}...")
        
        # If we have fewer than 3 papers, add general insights
        while len(insights) < 3 and self.topics:
            for i, topic in enumerate(self.topics):
                if i < 3 - len(insights):
                    insights.append(f"General insight on {topic}: More research may be needed in this area.")
        
        return insights[:3]  # Return top 3 insights
    
    def list_explored_papers(self) -> list:
        """
        Lists all papers explored, along with user notes and relevance marks.
        
        Returns:
            list: A list containing information on explored papers.
        """
        explored_papers = []
        for link, paper in self.papers.items():
            explored_papers.append({
                'link': link,
                'title': paper['title'],
                'authors': paper['authors'],
                'note': self.notes[link],
                'relevance': self.relevance[link]
            })
        return explored_papers
    
    def export_project_summary(self) -> dict:
        """
        Exports a summary of the project including project topics, papers,
        notes, and final insights.
        
        Returns:
            dict: A complete project summary.
        """
        summary = {
            'project_name': self.project_name,
            'project_topics': self.topics,
            'papers': self.list_explored_papers(),
            'final_insights': self.calculate_insights()
        }
        return summary


def get_papers(query: str) -> list:
    """
    A mock function that returns fixed example papers for test implementation.
    
    Args:
        query (str): The search query for which to return papers.
        
    Returns:
        list: A list of example papers.
    """
    example_papers = {
        "AI": [
            {"title": "Understanding AI", "authors": "A. Author", "abstract": "An introduction to AI concepts and principles.", "link": "link1.com"},
            {"title": "AI in Practice", "authors": "B. Author", "abstract": "AI applications in industry and research.", "link": "link2.com"},
            {"title": "Future of AI", "authors": "C. Author", "abstract": "Predictions for the future development of artificial intelligence.", "link": "link3.com"}
        ],
        "quantum computing": [
            {"title": "Quantum Mechanics", "authors": "D. Author", "abstract": "Basics of quantum mechanics for computing.", "link": "link4.com"},
            {"title": "Quantum Algorithms", "authors": "E. Author", "abstract": "Exploring quantum algorithms and their applications.", "link": "link5.com"},
            {"title": "Quantum Supremacy", "authors": "F. Author", "abstract": "Analysis of quantum supremacy experiments and results.", "link": "link6.com"}
        ],
        "climate change": [
            {"title": "Climate Overview", "authors": "G. Author", "abstract": "Overview of climate change issues and global impacts.", "link": "link7.com"},
            {"title": "Climate Solutions", "authors": "H. Author", "abstract": "Technical and policy solutions for climate change mitigation.", "link": "link8.com"},
            {"title": "Climate Models", "authors": "I. Author", "abstract": "Current climate modeling techniques and predictions.", "link": "link9.com"}
        ]
    }
    
    # Return the papers for the query if it exists, otherwise empty list
    return example_papers.get(query, [])