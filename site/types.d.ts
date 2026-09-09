declare module 'virtual:content-manifest' {
  export const researchItems: import('./content-types.js').ResearchItem[]
  export const searchItems: import('./content-types.js').SearchItem[]
}

declare module 'plotly.js-dist-min' {
  const Plotly: unknown
  export default Plotly
}
