import gradio as gr
from dotenv import load_dotenv
from github_client import PR_URL_PATTERN, GitHubAuthError
from pr_manager import PRManager

load_dotenv(override=True)

manager = PRManager()
comment_posted = False


async def analyze(pr_url: str):
    """Run the PR babysit process and stream progress/results back to the UI."""
    global comment_posted
    comment_posted = False

    if not pr_url or not pr_url.strip():
        yield "Please enter a GitHub PR URL.", gr.update(interactive=False), ""
        return

    if not PR_URL_PATTERN.match(pr_url.strip()):
        yield (
            "Invalid PR URL. Expected format: `https://github.com/owner/repo/pull/123`",
            gr.update(interactive=False),
            "",
        )
        return

    try:
        async for chunk in manager.run(pr_url.strip()):
            is_final = chunk.startswith("## Verdict:") or chunk.startswith("# PR")
            yield (
                chunk,
                gr.update(interactive=is_final),
                "",
            )
    except GitHubAuthError as exc:
        yield str(exc), gr.update(interactive=False), ""
    except ValueError as exc:
        yield str(exc), gr.update(interactive=False), ""
    except Exception as exc:
        yield f"Error: {exc}", gr.update(interactive=False), ""


def post_comment():
    """Post the last generated report as a PR comment."""
    global comment_posted
    if comment_posted:
        return (
            manager.last_report_markdown or "",
            gr.update(interactive=False),
            "Comment already posted.",
        )

    if not manager.last_report_markdown:
        return "", gr.update(interactive=False), "No report available. Run analysis first."

    import asyncio

    try:
        asyncio.run(manager.post_comment())
        comment_posted = True
        return (
            manager.last_report_markdown,
            gr.update(interactive=False),
            "Comment posted successfully.",
        )
    except Exception as exc:
        return (
            manager.last_report_markdown,
            gr.update(interactive=True),
            f"Failed to post comment: {exc}",
        )


def disable_buttons():
    return (
        gr.update(value="Processing...", interactive=False),
        gr.update(interactive=False),
        gr.Markdown("Analyzing PR...", visible=True),
    )


def enable_analyze_button():
    return (
        gr.update(value="Analyze", interactive=True),
        gr.Markdown("", visible=False),
    )


with gr.Blocks(theme=gr.themes.Default(primary_hue="sky")) as ui:
    gr.Markdown("# PR Merge-Readiness Agent")
    gr.Markdown(
        "Enter a GitHub PR URL. A team of agents will triage CI failures and review "
        "comments, then propose scoped fixes **without pushing commits**."
    )

    pr_url_input = gr.Textbox(
        label="GitHub PR URL",
        placeholder="https://github.com/owner/repo/pull/123",
    )

    with gr.Row():
        analyze_button = gr.Button("Analyze", variant="primary")
        post_comment_button = gr.Button("Post comment to PR", interactive=False)

    status_text = gr.Markdown("", visible=False)
    report_output = gr.Markdown(label="Report")
    comment_status = gr.Markdown(label="Comment status")

    run_analysis = (
        analyze_button.click(
            fn=disable_buttons,
            outputs=[analyze_button, post_comment_button, status_text],
            queue=False,
        )
        .then(
            fn=analyze,
            inputs=pr_url_input,
            outputs=[report_output, post_comment_button, comment_status],
            show_progress="full",
        )
        .then(
            fn=enable_analyze_button,
            outputs=[analyze_button, status_text],
            queue=False,
        )
    )

    pr_url_input.submit(
        fn=disable_buttons,
        outputs=[analyze_button, post_comment_button, status_text],
        queue=False,
    ).then(
        fn=analyze,
        inputs=pr_url_input,
        outputs=[report_output, post_comment_button, comment_status],
        show_progress="full",
    ).then(
        fn=enable_analyze_button,
        outputs=[analyze_button, status_text],
        queue=False,
    )

    post_comment_button.click(
        fn=post_comment,
        outputs=[report_output, post_comment_button, comment_status],
    )

ui.queue()
ui.launch(inbrowser=True)
