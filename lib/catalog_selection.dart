/// Whether a reviewed catalog description can be offered for collection.
bool collectableCatalogRecord(Map record) =>
    record['metadata_reviewed'] == true &&
    record['reuse_status'] == 'user_approved' &&
    record['reuse_approval'] is Map &&
    (record['reuse_approval'] as Map).isNotEmpty &&
    (record['description'] as String? ?? '').length >= 40;

/// Returns only eligible URLs explicitly retained in the current selection.
List<String> selectedCatalogSources(List records, Set<String> excluded) => [
  for (final Map record in records)
    if (collectableCatalogRecord(record) && !excluded.contains(record['source']))
      record['source'] as String,
];
