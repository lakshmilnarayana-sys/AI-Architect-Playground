# n8n Workflows

This folder contains importable n8n workflow templates.

## Code Review ReAct Agent (GitHub PR)

File: `Code Review ReAct Agent (GitHub PR).json`

This workflow reviews GitHub pull requests with a ReAct-style AI agent. It listens for GitHub `pull_request` events, fetches the PR diff, runs deterministic code review tools, asks an OpenAI chat model to produce a structured review, and posts the result back to the pull request as a non-blocking GitHub review comment.

### Workflow

1. `GitHub Trigger` receives pull request events.
2. `Filter PR Events` keeps relevant PR activity.
3. `Fetch Diff` downloads the pull request diff from GitHub.
4. `Parse Input` prepares the diff and context for the agent.
5. `Code Review Agent` reviews the diff using these tools:
   - `get_code`
   - `ast_complexity_analysis`
   - `security_analysis`
   - `quality_regex_analysis`
   - `web_search`
6. `Format Output` prepares the final report.
7. `Create a review` posts the review comment to GitHub.

### Requirements

- n8n with LangChain nodes available.
- GitHub OAuth2 credential in n8n.
- OpenAI API credential in n8n.
- Repository permissions that allow reading pull requests and creating pull request reviews.

### Import

1. Open n8n.
2. Go to **Workflows**.
3. Select **Import from File**.
4. Choose `Code Review ReAct Agent (GitHub PR).json`.
5. Reconnect credentials for:
   - `GitHub Trigger`
   - `Fetch Diff`
   - `Create a review`
   - `OpenAI Chat Model`

### Configure

After import, update the GitHub owner and repository values in both:

- `GitHub Trigger`
- `Create a review`

The exported workflow currently contains example repository values from the source environment. Replace them with the target repository before activating the workflow.

The `OpenAI Chat Model` node uses `gpt-4o-mini` with temperature `0.2`. Adjust the model only if your n8n instance has a different approved model or budget requirement.

### Activate

Activate the workflow in n8n after credentials and repository values are configured. An active workflow registers the real GitHub webhook. Test/listen mode is not enough for production PR review automation.

By default, the workflow posts reviews with `event=comment`, so it does not block merges. To make the review gating, update the `Create a review` node event setting according to your repository policy.
