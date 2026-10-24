export function citationKeys(markdown: string): string[] {
  return [
    ...new Set(
      Array.from(markdown.matchAll(/\[(S\d+)\]/g), (match) => match[1]),
    ),
  ];
}

export function linkCitations(markdown: string): string {
  return markdown.replace(/\[(S\d+)\]/g, "[$1](#citation-$1)");
}
