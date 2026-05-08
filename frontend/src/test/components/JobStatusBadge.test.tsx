import { render, screen } from "@testing-library/react";
import { JobStatusBadge } from "@/components/common/JobStatusBadge";

describe("JobStatusBadge", () => {
  it("renders 'Pending' for pending status", () => {
    render(<JobStatusBadge status="pending" />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders 'Running' for running status", () => {
    render(<JobStatusBadge status="running" />);
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("renders 'Done' for done status", () => {
    render(<JobStatusBadge status="done" />);
    expect(screen.getByText("Done")).toBeInTheDocument();
  });

  it("renders 'Failed' for failed status", () => {
    render(<JobStatusBadge status="failed" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("applies animate-pulse class when running", () => {
    const { container } = render(<JobStatusBadge status="running" />);
    expect(container.firstChild).toHaveClass("animate-pulse");
  });
});
