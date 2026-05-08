import { render, screen } from "@testing-library/react";
import { AlertLevelBadge } from "@/components/common/AlertLevelBadge";

describe("AlertLevelBadge", () => {
  it("renders the level text", () => {
    render(<AlertLevelBadge level="RED" />);
    expect(screen.getByText("RED")).toBeInTheDocument();
  });

  it("applies red styling for RED level", () => {
    const { container } = render(<AlertLevelBadge level="RED" />);
    expect(container.firstChild).toHaveClass("bg-red-100");
  });

  it("applies green styling for GREEN level", () => {
    const { container } = render(<AlertLevelBadge level="GREEN" />);
    expect(container.firstChild).toHaveClass("bg-green-100");
  });

  it("shows score when provided", () => {
    render(<AlertLevelBadge level="ORANGE" showScore={65} />);
    expect(screen.getByText("65", { exact: false })).toBeInTheDocument();
  });
});
