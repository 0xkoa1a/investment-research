export interface PlotReference {
  chart: string
  caption: string
}

export interface ResearchItem {
  type: 'research'
  title: string
  summary: string
  updated?: string
  dataAsOf?: string
  path: string
  slug: string
}

export interface SearchItem {
  type: 'research'
  title: string
  summary: string
  headings: string[]
  body: string
  path: string
}

export interface ResearchContract {
  slug: string
  source: string
  dataAsOf?: string
  plots: PlotReference[]
}

export interface ContentManifest {
  research: ResearchItem[]
  search: SearchItem[]
  contracts: ResearchContract[]
}
