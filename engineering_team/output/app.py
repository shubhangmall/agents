import gradio as gr
import research_agent as ra

# Initialize a research assistant with a default project name
# In a real app, we might let users create multiple projects
assistant = ra.ResearchAssistant("My Research Project")

# Functions for Gradio components
def create_project(project_name):
    global assistant
    assistant = ra.ResearchAssistant(project_name)
    return f"Created new research project: {project_name}"

def add_topic(topic):
    if not topic:
        return "Please enter a topic."
    assistant.add_topic(topic)
    return f"Added topic: {topic}"

def get_topics():
    return ", ".join(assistant.topics) if assistant.topics else "No topics added yet."

def fetch_papers(query):
    if not query:
        return "Please enter a search query."
    assistant.add_papers(query)
    papers = [p for p in assistant.papers.values()]
    
    if not papers:
        return "No papers found for this query."
    
    result = ""
    for paper in papers:
        result += f"Title: {paper['title']}\n"
        result += f"Authors: {paper['authors']}\n"
        result += f"Abstract: {paper['abstract']}\n"
        result += f"Link: {paper['link']}\n\n"
    
    return result

def list_papers():
    papers = assistant.list_explored_papers()
    
    if not papers:
        return "No papers have been fetched yet."
    
    result = ""
    for paper in papers:
        relevance_str = "Relevant" if paper['relevance'] is True else "Not relevant" if paper['relevance'] is False else "Not marked"
        result += f"Title: {paper['title']}\n"
        result += f"Authors: {paper['authors']}\n"
        result += f"Link: {paper['link']}\n"
        result += f"Notes: {paper['note']}\n"
        result += f"Relevance: {relevance_str}\n\n"
    
    return result

def add_note(paper_link, note, relevance):
    if not paper_link:
        return "Please enter a paper link."
    
    if paper_link not in assistant.papers:
        return f"Paper with link '{paper_link}' not found."
    
    assistant.record_notes(paper_link, note)
    if relevance == "Relevant":
        assistant.mark_relevance(paper_link, True)
    elif relevance == "Not relevant":
        assistant.mark_relevance(paper_link, False)
    
    return f"Updated notes and relevance for paper: {assistant.papers[paper_link]['title']}"

def summarize_abstracts():
    summaries = assistant.summarize_abstracts()
    
    if not summaries:
        return "No papers to summarize."
    
    result = "--- Abstract Summaries ---\n\n"
    for link, summary in summaries.items():
        result += f"{summary}\n\n"
    
    return result

def compare_papers(topic):
    if not topic:
        return "Please enter a topic for comparison."
    
    comparison = assistant.compare_papers(topic)
    
    if "error" in comparison:
        return comparison["error"]
    
    if "message" in comparison:
        return comparison["message"]
    
    result = f"--- Comparison of Papers on {topic} ---\n\n"
    result += f"Number of papers: {comparison['paper_count']}\n\n"
    
    for link, paper_info in comparison['papers'].items():
        result += f"Title: {paper_info['title']}\n"
        result += f"Authors: {paper_info['authors']}\n"
        result += f"Summary: {paper_info['abstract_summary']}\n\n"
    
    result += f"Common themes: {comparison['common_themes']}\n"
    result += f"Differences: {comparison['differences']}\n"
    
    return result

def get_insights():
    insights = assistant.calculate_insights()
    
    if not insights:
        return "No insights available. Try adding more papers first."
    
    result = "--- Top 3 Key Insights ---\n\n"
    for i, insight in enumerate(insights, 1):
        result += f"{i}. {insight}\n\n"
    
    return result

def export_summary():
    summary = assistant.export_project_summary()
    
    result = f"--- Project Summary: {summary['project_name']} ---\n\n"
    result += "Topics: " + ", ".join(summary['project_topics']) + "\n\n"
    
    result += "Papers:\n"
    for paper in summary['papers']:
        relevance_str = "Relevant" if paper['relevance'] is True else "Not relevant" if paper['relevance'] is False else "Not marked"
        result += f"- {paper['title']} by {paper['authors']}\n"
        result += f"  Link: {paper['link']}\n"
        result += f"  Notes: {paper['note']}\n"
        result += f"  Relevance: {relevance_str}\n\n"
    
    result += "Key Insights:\n"
    for i, insight in enumerate(summary['final_insights'], 1):
        result += f"{i}. {insight}\n\n"
    
    return result

# Create the Gradio interface
with gr.Blocks(title="Research Assistant") as demo:
    gr.Markdown("# Academic Research Assistant")
    gr.Markdown("A tool to help explore and organize academic papers")
    
    with gr.Tab("Project Setup"):
        with gr.Row():
            project_name_input = gr.Textbox(label="Project Name")
            create_btn = gr.Button("Create Project")
        project_output = gr.Textbox(label="Output", interactive=False)
        create_btn.click(create_project, inputs=project_name_input, outputs=project_output)
        
        gr.Markdown("### Add Research Topics")
        with gr.Row():
            topic_input = gr.Textbox(label="Topic/Keyword")
            add_topic_btn = gr.Button("Add Topic")
        topic_output = gr.Textbox(label="Output", interactive=False)
        topics_display = gr.Textbox(label="Current Topics", interactive=False)
        refresh_topics_btn = gr.Button("Refresh Topics List")
        
        add_topic_btn.click(add_topic, inputs=topic_input, outputs=topic_output)
        refresh_topics_btn.click(get_topics, inputs=None, outputs=topics_display)
    
    with gr.Tab("Paper Search"):
        gr.Markdown("### Search for Papers")
        with gr.Row():
            search_input = gr.Textbox(label="Search Query")
            search_btn = gr.Button("Search")
        search_output = gr.Textbox(label="Search Results", interactive=False, lines=15)
        search_btn.click(fetch_papers, inputs=search_input, outputs=search_output)
        
        gr.Markdown("### All Explored Papers")
        list_papers_btn = gr.Button("List All Papers")
        papers_list_output = gr.Textbox(label="Papers List", interactive=False, lines=15)
        list_papers_btn.click(list_papers, inputs=None, outputs=papers_list_output)
    
    with gr.Tab("Notes & Relevance"):
        gr.Markdown("### Add Notes and Mark Relevance")
        paper_link_input = gr.Textbox(label="Paper Link")
        note_input = gr.Textbox(label="Your Notes", lines=5)
        relevance_input = gr.Radio(["Relevant", "Not relevant", "Not sure"], label="Relevance")
        save_note_btn = gr.Button("Save Notes & Relevance")
        note_output = gr.Textbox(label="Output", interactive=False)
        
        save_note_btn.click(add_note, inputs=[paper_link_input, note_input, relevance_input], outputs=note_output)
    
    with gr.Tab("Analysis"):
        gr.Markdown("### Paper Analysis Tools")
        
        with gr.Accordion("Abstract Summaries"):
            summarize_btn = gr.Button("Generate Abstract Summaries")
            summary_output = gr.Textbox(label="Summaries", interactive=False, lines=10)
            summarize_btn.click(summarize_abstracts, inputs=None, outputs=summary_output)
        
        with gr.Accordion("Compare Papers on a Topic"):
            compare_topic_input = gr.Textbox(label="Topic for Comparison")
            compare_btn = gr.Button("Compare Papers")
            comparison_output = gr.Textbox(label="Comparison", interactive=False, lines=10)
            compare_btn.click(compare_papers, inputs=compare_topic_input, outputs=comparison_output)
        
        with gr.Accordion("Key Insights"):
            insights_btn = gr.Button("Calculate Key Insights")
            insights_output = gr.Textbox(label="Insights", interactive=False, lines=10)
            insights_btn.click(get_insights, inputs=None, outputs=insights_output)
    
    with gr.Tab("Export"):
        gr.Markdown("### Export Project Summary")
        export_btn = gr.Button("Generate Project Summary")
        export_output = gr.Textbox(label="Project Summary", interactive=False, lines=20)
        export_btn.click(export_summary, inputs=None, outputs=export_output)

if __name__ == "__main__":
    demo.launch()