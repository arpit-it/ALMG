/// Port for the local backend, overridable in builds used with local fixtures.
const backendPort = int.fromEnvironment(
  'ALMG_BACKEND_PORT',
  defaultValue: 8766,
);
