import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { GradingListView } from "@/components/grading-list-view";
import { GradingWorkspaceNav } from "@/components/grading-workspace-nav";
import type { GradingListRow } from "@/lib/grading-ui";

const rows: GradingListRow[] = [
  {
    id: "cat_1",
    name: "The Lassi Pub",
    location: "Indiranagar, Bangalore",
    type: "restaurant",
    typeLabel: "Restaurant",
    platformLabel: "Swiggy",
    thumbnail: "https://cdn.example/lassi.jpg",
    letter: "B",
    score: 78,
  },
  {
    id: "cat_2",
    name: "Cochin Village",
    location: "Koramangala",
    type: "dineout",
    typeLabel: "Dineout",
    platformLabel: "Zomato",
    thumbnail: null,
    letter: null,
    score: null,
  },
];

describe("grading owner views", () => {
  it("lists restaurants and dineouts with overall grades", () => {
    const html = renderToStaticMarkup(
      <GradingListView rows={rows} domain="all" grade="all" onDomain={() => undefined} onGrade={() => undefined} />,
    );
    expect(html).toContain("The Lassi Pub");
    expect(html).toContain("Cochin Village");
    expect(html).toContain("Restaurant");
    expect(html).toContain("Dineout");
    expect(html).toContain(">B<");
    expect(html).toContain("Not graded");
    expect(html).toContain("/grading/cat_1");
    expect(html).toContain("/grading/cat_2");
  });

  it("opens quality, photos, and video in the grading workspace", () => {
    const html = renderToStaticMarkup(<GradingWorkspaceNav catalogueId="cat_1" active="photos" />);
    expect(html).toContain("Quality");
    expect(html).toContain("Photos");
    expect(html).toContain("Video");
    expect(html).toContain("/grading/cat_1");
    expect(html).toContain("/grading/cat_1?tab=photos");
    expect(html).toContain("/grading/cat_1?tab=video");
    expect(html).toContain("/catalogues/cat_1/improvements");
    expect(html).toContain("/catalogues/cat_1/reviews");
  });
});
