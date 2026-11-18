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

/// Whether a reviewed abstract has permission and enough text for collection.
bool collectablePublication(Map record) =>
    record['abstract_reviewed'] == true &&
    record['reuse_status'] == 'user_approved' &&
    record['reuse_approval'] is Map &&
    (record['abstract'] as String? ?? '').length >= 40;

/// Whether entity text has permission and enough content for classification.
bool collectableEntity(Map record) =>
    record['reuse_status'] == 'user_approved' && record['reuse_approval'] is Map &&
    "${record['title']}\n${record['description']}".length >= 40;

/// Whether a catalog description has metadata-scoped permission and usable text.
bool collectableIndicator(Map record) =>
    record['reuse_status'] == 'user_approved' && record['reuse_approval'] is Map &&
    record['reuse_approval']['scope'] == 'catalog_description' &&
    "${record['title']}\n${record['description']}".length >= 40;

/// Whether a reviewed document summary can be offered for collection.
bool collectableNotice(Map record) =>
    record['summary_reviewed'] == true && record['reuse_status'] == 'user_approved' &&
    record['reuse_approval'] is Map && record['reuse_approval']['scope'] == 'document_summary' &&
    "${record['title']}\n${record['summary']}".length >= 40;

/// Whether the displayed abstract has scoped permission and usable text.
bool collectableBibliography(Map record) =>
    record['abstract_reviewed'] == true && record['reuse_status'] == 'user_approved' &&
    record['reuse_approval'] is Map && record['reuse_approval']['scope'] == 'crossref_abstract' &&
    (record['abstract'] as String? ?? '').length >= 40;

/// Whether a filing preview has scoped permission and enough text to collect.
bool collectableFiling(Map record) =>
    record['filing_reviewed'] == true && record['reuse_status'] == 'user_approved' &&
    record['reuse_approval'] is Map && record['reuse_approval']['scope'] == 'sec_filing_preview' &&
    (record['filing_text'] as String? ?? '').length >= 40;

/// Whether the website page preview has reuse permission and usable text.
bool collectableWebsitePage(Map record) =>
    record['page_reviewed'] == true && record['reuse_status'] == 'user_approved' &&
    record['reuse_approval'] is Map && record['reuse_approval']['scope'] == 'website_page_preview' &&
    (record['page_text'] as String? ?? '').length >= 40;
