#!/bin/bash
# Setup script for Claude Code coding agent on a new device

set -e

echo "🤖 Claude Code Coding Agent Setup"
echo "=================================="
echo ""

# Install Claude Code if not present
if ! command -v claude &> /dev/null; then
    echo "📦 Installing Claude Code..."
    
    # Try global install, fallback to user-local
    if npm install -g @anthropic-ai/claude-code 2>/dev/null; then
        echo "✅ Claude Code installed globally"
    else
        echo "📦 Trying user-local install..."
        mkdir -p ~/.npm-global
        export npm_config_prefix=~/.npm-global
        export PATH=~/.npm-global/bin:$PATH
        npm install -g @anthropic-ai/claude-code
        echo "✅ Claude Code installed to ~/.npm-global/"
    fi
fi

echo "✅ Claude Code installed: $(claude --version)"

# Check GitHub access
echo ""
echo "📋 Checking GitHub access..."

if [ -n "$GITHUB_TOKEN" ]; then
    echo "✅ GITHUB_TOKEN env var set"
elif command -v gh &> /dev/null && gh auth status &> /dev/null; then
    echo "✅ GitHub CLI authenticated"
else
    echo "⚠️  No GitHub access detected. Options:"
    echo "   1. Set GITHUB_TOKEN env var"
    echo "   2. Run: brew install gh && gh auth login"
fi

# Check required tools
echo ""
echo "🔧 Checking tools..."

for tool in git nix rustc cargo; do
    if command -v $tool &> /dev/null; then
        echo "  ✅ $tool"
    else
        echo "  ⚠️  $tool not found"
    fi
done

# Check key repos
echo ""
echo "📁 Checking key repos..."

repos=(
    "logos-scaffold"
    "lez-framework"
    "lez-multisig"
    "lssa"
)

for repo in "${repos[@]}"; do
    if [ -d "$HOME/$repo" ] || [ -d "$HOME/$repo.git" ]; then
        echo "  ✅ $repo"
    else
        echo "  ⚠️  $repo not found (will need: git clone ...)"
    fi
done

echo ""
echo "📝 Next steps:"
echo "   1. If Claude Code not logged in: claude /login"
echo "   2. Clone any missing repos above"
echo "   3. You're ready to code!"
echo ""
echo "To use Claude Code as coding agent:"
echo "   claude -p 'Your task here'"
echo ""
echo "Or with background mode:"
echo "   bash pty:true workdir:~/project background:true command:\"claude 'Your task'\""