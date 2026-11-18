import 'package:flutter_test/flutter_test.dart';
import 'package:idle_model_studio/indicator_filter.dart';

void main() {
  final population = {'indicator_id': 'SP.POP.TOTL', 'title': 'Population, total',
    'description': 'All residents', 'source_name': 'Development indicators', 'organization': 'Fixture statistics'};
  final gdp = {'indicator_id': 'NY.GDP.MKTP.CD', 'title': 'GDP',
    'description': 'Economic output', 'source_name': 'National accounts'};
  test('filter matches terms across loaded metadata without changing source records', () {
    expect(filterIndicators([population, gdp], ' POPULATION   residents '), [population]);
    expect(filterIndicators([population, gdp], 'sp.pop.totl statistics'), [population]);
    expect(filterIndicators([population, gdp], 'accounts output'), [gdp]);
    expect(filterIndicators([population, gdp], 'population output'), isEmpty);
    expect(filterIndicators([population, gdp], '  '), [population, gdp]);
    expect(population['title'], 'Population, total');
  });
}
