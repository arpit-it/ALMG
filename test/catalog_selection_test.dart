import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/catalog_selection.dart';

void main() {
  test('website page eligibility requires preview scope and enough text', () {
    final record = {'page_reviewed': true, 'reuse_status': 'user_approved',
      'reuse_approval': {'scope': 'website_page_preview'}, 'page_text': 'a' * 40};
    expect(collectableWebsitePage(record), isTrue);
    expect(collectableWebsitePage({...record, 'page_text': 'a' * 39}), isFalse);
    expect(collectableWebsitePage({...record, 'page_reviewed': false}), isFalse);
    expect(collectableWebsitePage({...record, 'reuse_approval': {'scope': 'whole_site'}}), isFalse);
  });
  test('Crossref collection requires reviewed scoped permission and 40 characters', () {
    final record = {
      'abstract_reviewed': true, 'reuse_status': 'user_approved',
      'reuse_approval': {'scope': 'crossref_abstract'}, 'abstract': 'a' * 40,
    };
    expect(collectableBibliography(record), isTrue);
    expect(collectableBibliography({...record, 'abstract': 'a' * 39}), isFalse);
    expect(collectableBibliography({...record, 'abstract_reviewed': false}), isFalse);
    expect(collectableBibliography({...record, 'reuse_status': 'unverified'}), isFalse);
    expect(collectableBibliography({...record, 'reuse_approval': {'scope': 'publisher_page'}}), isFalse);
  });
  test('collection contains only selected records with reviewed permission', () {
    final record = {
      'source': 'https://www.loc.gov/item/12345/',
      'metadata_reviewed': true,
      'reuse_status': 'user_approved',
      'reuse_approval': {'permission_basis': 'Fixture permission'},
      'description': 'A catalog description long enough for dataset collection.',
    };
    final other = {...record, 'source': 'https://www.loc.gov/item/54321/'};
    final records = [record, other,
      {...record, 'metadata_reviewed': false},
      {...record, 'reuse_approval': <String, dynamic>{}},
      {...record, 'reuse_status': 'unverified'},
      {...record, 'description': 'Too short'},
    ];
    expect(selectedCatalogSources(records, {}), [record['source'], other['source']]);
    expect(selectedCatalogSources(records, {record['source'] as String}), [other['source']]);
    expect(selectedCatalogSources([record, other], {
      record['source'] as String, other['source'] as String,
    }), isEmpty);
    expect(record['reuse_approval'], isNotEmpty);
  });
}
