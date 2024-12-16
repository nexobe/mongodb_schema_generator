#!/bin/bash

# Checkout to a temporary branch
git checkout --orphan temp_branch

# Add all files
git add -A

# Commit the changes
git commit -m "Initial commit"

# Delete the old branch
git branch -D main

# Rename the temporary branch to main
git branch -m main

# Force push to remote repository
echo "To force push and clear remote history, run:"
echo "git push -f origin main"
