import 'dart:typed_data';

/// Runs an ALMG shape model in Dart using the weights from its exported JSON.
/// The output is 8-bit RGB in row-major order.
class ShapeImageModel {
  ShapeImageModel(Map<String, dynamic> model)
    : size = model['size'] as int,
      _background = model['background'] as int,
      _palette = model['palette'] as Map<String, dynamic>,
      _masks = model['masks'] as Map<String, dynamic> {
    if (model['format'] != 'almg-shapes-v1' || size != 48) {
      throw const FormatException('Unsupported ALMG image model.');
    }
  }

  final int size;
  final int _background;
  final Map<String, dynamic> _palette;
  final Map<String, dynamic> _masks;

  /// Composes up to three colored shapes using the exported weights.
  Uint8List generate(String prompt) {
    final clauses = prompt.trim().toLowerCase().split(
      RegExp(r'\s+\band\b\s+|\s*,\s*'),
    );
    const defaults = [
      ['center'],
      ['left', 'right'],
      ['left', 'center', 'right'],
    ];
    if (clauses.length > defaults.length) {
      throw const FormatException(
        'The image model supports up to three shapes per image.',
      );
    }
    final pixels = Uint8List(size * size * 3)
      ..fillRange(0, size * size * 3, _background);
    final shapeNames = _masks.keys.map((key) => key.split(':').first).toSet();
    for (var item = 0; item < clauses.length; item++) {
      final tokens = RegExp('[a-z]+')
          .allMatches(clauses[item])
          .map((match) => match.group(0)!)
          .toSet();
      final colors = tokens.intersection(_palette.keys.toSet());
      final shapes = tokens.intersection(shapeNames);
      final positions = tokens.intersection({'left', 'center', 'right'});
      if (colors.length != 1 || shapes.length != 1 || positions.length > 1) {
        throw const FormatException(
          'Describe one supported color and shape per item, e.g. '
          'a red circle and a blue square.',
        );
      }
      final position = positions.isEmpty
          ? defaults[clauses.length - 1][item]
          : positions.single;
      final mask = _masks['${shapes.single}:$position'] as List;
      final color = (_palette[colors.single] as List).cast<int>();
      for (var index = 0; index < mask.length; index++) {
        if ((mask[index] as num) >= 0.5) {
          pixels.setRange(index * 3, index * 3 + 3, color);
        }
      }
    }
    return pixels;
  }
}
