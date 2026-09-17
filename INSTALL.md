# Forge Agent Kit

## Install

Copy the contents of this kit into the Forge repository root.

Then inspect the resulting files before committing them.

## Build sandbox

cd sandbox
docker build -t forge-agent .

## Copilot

From the Forge repository root, start Copilot CLI and run:

/sandbox enable
/sandbox policy

Verify the effective filesystem policy is limited to the current Forge workspace and that network access is configured according to the task.

Do not use --allow-all or --yolo for this first setup.

## First mission

Run the discovery prompt in .github/prompts/discover-forge.md.

The discovery mission is read-only with respect to application architecture. It should populate the agent documentation before any major refactor is attempted.
