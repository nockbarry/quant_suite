"""Theses panel — active theses with conviction levels."""

from textual.widgets import Static


class ThesesPanel(Static):
    """Active theses from YAML files, with conviction bars."""

    def refresh_data(self) -> None:
        lines = ["[b]THESES[/b]", ""]
        try:
            from src.core.paths import paths
            from src.knowledge.thesis import ThesisTracker

            tracker = ThesisTracker(paths.theses)
            theses = tracker.get_active_theses()

            if not theses:
                lines.append("  [dim]No active theses[/dim]")
                self.update("\n".join(lines))
                return

            # Sort by conviction descending
            theses.sort(key=lambda t: t.conviction, reverse=True)

            for t in theses[:10]:
                bar = _conviction_bar(t.conviction)
                color = (
                    "green" if t.conviction >= 75
                    else "yellow" if t.conviction >= 50
                    else "red"
                )
                name = t.name[:20]
                lines.append(
                    f"  {name:<20} [{color}]{t.conviction:>3.0f}%[/{color}] {bar}"
                )

        except Exception as e:
            lines.append(f"  [red]Error: {e}[/red]")

        self.update("\n".join(lines))


def _conviction_bar(conviction: float, width: int = 10) -> str:
    filled = int(conviction / 100 * width)
    return "[green]" + "█" * filled + "[/green]" + "[dim]░[/dim]" * (width - filled)
