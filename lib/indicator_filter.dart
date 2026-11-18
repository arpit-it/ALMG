/// Matches all entered terms against metadata already loaded on this machine.
List<Map> filterIndicators(List records, String query) {
  final terms = query.trim().toLowerCase().split(RegExp(r'\s+')).where((term) => term.isNotEmpty);
  return [
    for (final Map record in records)
      if (terms.every((term) => [
        record['indicator_id'], record['title'], record['description'],
        record['source_name'], record['organization'],
      ].whereType<String>().join(' ').toLowerCase().contains(term))) record,
  ];
}
