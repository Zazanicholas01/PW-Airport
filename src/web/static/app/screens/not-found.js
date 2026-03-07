export const notFoundScreen = {
  render() {
    return `
      <section class="placeholder-screen">
        <h2>Route Not Found</h2>
        <p class="muted">The requested dashboard route is not registered.</p>
        <a class="app-nav-link" href="#/overview">Back To Overview</a>
      </section>
    `;
  },
};
