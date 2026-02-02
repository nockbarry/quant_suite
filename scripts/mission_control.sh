#!/bin/bash
# Mission Control - Unified monitoring for Project Athena
#
# Usage:
#   ./scripts/mission_control.sh           # Launch tmux session with all dashboards
#   ./scripts/mission_control.sh --quick   # Quick status check (no tmux)
#   ./scripts/mission_control.sh --attach  # Attach to existing session
#   ./scripts/mission_control.sh --kill    # Kill existing session

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SESSION_NAME="athena-control"

cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

show_help() {
    echo "Mission Control - Project Athena Monitoring"
    echo ""
    echo "Usage: $0 [option]"
    echo ""
    echo "Options:"
    echo "  (no args)    Launch tmux session with all dashboards"
    echo "  --quick      Quick status check (single terminal, no tmux)"
    echo "  --attach     Attach to existing session"
    echo "  --kill       Kill existing session"
    echo "  --swarm      Launch swarm visualizer only"
    echo "  --portfolio  Launch portfolio dashboard only"
    echo "  --help       Show this help"
    echo ""
    echo "Tmux Layout:"
    echo "  ┌─────────────────────┬─────────────────────┐"
    echo "  │                     │                     │"
    echo "  │  Unified Dashboard  │  Swarm Visualizer   │"
    echo "  │  (main view)        │  (agent activity)   │"
    echo "  │                     │                     │"
    echo "  ├─────────────────────┴─────────────────────┤"
    echo "  │               Portfolio Status            │"
    echo "  │           (positions, P&L, alerts)        │"
    echo "  └───────────────────────────────────────────┘"
    echo ""
    echo "In tmux session:"
    echo "  Ctrl+b + arrow keys  - Navigate between panes"
    echo "  Ctrl+b + z           - Zoom current pane (toggle)"
    echo "  Ctrl+b + d           - Detach from session"
    echo "  Ctrl+c               - Stop current dashboard"
}

quick_check() {
    echo -e "${BLUE}=== ATHENA QUICK STATUS ===${NC}"
    echo ""

    # Run unified dashboard once
    PYTHONPATH="$PROJECT_DIR" python3 -m src.monitoring.unified_dashboard 2>/dev/null

    echo ""
    echo -e "${YELLOW}For full monitoring: $0${NC}"
}

launch_swarm() {
    echo -e "${BLUE}Launching Swarm Visualizer...${NC}"
    PYTHONPATH="$PROJECT_DIR" python3 -m src.monitoring.swarm_visualizer --watch --interval 15
}

launch_portfolio() {
    echo -e "${BLUE}Launching Portfolio Dashboard...${NC}"
    PYTHONPATH="$PROJECT_DIR" python3 -m src.execution.monitoring.cli_dashboard --mode paper --refresh 10
}

kill_session() {
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        tmux kill-session -t "$SESSION_NAME"
        echo -e "${GREEN}Session '$SESSION_NAME' killed${NC}"
    else
        echo -e "${YELLOW}No session '$SESSION_NAME' found${NC}"
    fi
}

attach_session() {
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        tmux attach-session -t "$SESSION_NAME"
    else
        echo -e "${RED}No session '$SESSION_NAME' found. Run without args to create.${NC}"
        exit 1
    fi
}

launch_mission_control() {
    # Check if tmux is installed
    if ! command -v tmux &> /dev/null; then
        echo -e "${RED}tmux is not installed. Install with: sudo apt install tmux${NC}"
        echo -e "${YELLOW}Running quick check instead...${NC}"
        quick_check
        exit 1
    fi

    # Kill existing session if it exists
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo -e "${YELLOW}Killing existing session...${NC}"
        tmux kill-session -t "$SESSION_NAME"
    fi

    echo -e "${GREEN}Launching Mission Control...${NC}"

    # Create new session with unified dashboard (main pane)
    tmux new-session -d -s "$SESSION_NAME" -x 200 -y 50 \
        "cd $PROJECT_DIR && PYTHONPATH=$PROJECT_DIR python3 -m src.monitoring.unified_dashboard --watch; exec bash"

    # Split horizontally for swarm visualizer (right pane)
    tmux split-window -h -t "$SESSION_NAME" \
        "cd $PROJECT_DIR && PYTHONPATH=$PROJECT_DIR python3 -m src.monitoring.swarm_visualizer --watch --interval 15; exec bash"

    # Split the right pane vertically for logs/alerts
    tmux split-window -v -t "$SESSION_NAME" \
        "cd $PROJECT_DIR && echo 'System Logs (tail -f)' && tail -f ~/quant_results/logs/operator_log.jsonl 2>/dev/null || echo 'No logs yet. Press any key...'; read; exec bash"

    # Create bottom pane for portfolio (split left pane)
    tmux select-pane -t "$SESSION_NAME:0.0"
    tmux split-window -v -t "$SESSION_NAME" \
        "cd $PROJECT_DIR && PYTHONPATH=$PROJECT_DIR python3 -m src.monitoring.comprehensive_dashboard --watch; exec bash"

    # Set pane sizes (approximate 60/40 horizontal, 70/30 vertical)
    tmux select-layout -t "$SESSION_NAME" tiled

    # Set window title
    tmux rename-window -t "$SESSION_NAME" "Mission Control"

    # Select the main pane (unified dashboard)
    tmux select-pane -t "$SESSION_NAME:0.0"

    echo -e "${GREEN}Mission Control launched!${NC}"
    echo ""
    echo "Attaching to session..."
    echo "  Ctrl+b + arrow keys - Navigate panes"
    echo "  Ctrl+b + z          - Zoom pane"
    echo "  Ctrl+b + d          - Detach"
    echo ""

    # Attach to session
    tmux attach-session -t "$SESSION_NAME"
}

# Parse arguments
case "$1" in
    --help|-h)
        show_help
        ;;
    --quick|-q)
        quick_check
        ;;
    --attach|-a)
        attach_session
        ;;
    --kill|-k)
        kill_session
        ;;
    --swarm|-s)
        launch_swarm
        ;;
    --portfolio|-p)
        launch_portfolio
        ;;
    "")
        launch_mission_control
        ;;
    *)
        echo -e "${RED}Unknown option: $1${NC}"
        show_help
        exit 1
        ;;
esac
