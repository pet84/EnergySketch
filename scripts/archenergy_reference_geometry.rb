# encoding: UTF-8
# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
# Read-only per-face oracle in the separately owned native reference process.
require 'json'
require 'digest'
config = JSON.parse(File.binread(ENV.fetch('ARCHSKETCH_REFERENCE_CONFIG')).force_encoding('UTF-8'))
raise 'Wrong owned process' unless Process.pid == config.fetch('expected_pid') && ENV['ARCHSKETCH_REFERENCE_NONCE'] == config.fetch('nonce')
source = config.fetch('source')
raise 'Source must be an isolated evidence COPY' unless File.expand_path(source).tr('\\','/').start_with?((File.expand_path('../output/archenergy', File.dirname(__FILE__)).tr('\\', '/') + '/'))
model = Sketchup.active_model
raise 'Wrong source model' unless File.expand_path(model.path).downcase == File.expand_path(source).downcase
raise 'Wrong source bytes' unless Digest::SHA256.file(source).hexdigest == config.fetch('source_sha256')
output = File.expand_path(config.fetch('output'))
raise 'Output outside evidence folder' unless output.tr('\\','/').start_with?((File.expand_path('../output/archenergy', File.dirname(__FILE__)).tr('\\', '/') + '/'))
faces = []
walk = nil
walk = lambda do |entities, transform, path|
  entities.each do |entity|
    if entity.is_a?(Sketchup::Face)
      mesh = entity.mesh(7)
      loops = [entity.outer_loop] + entity.loops.reject { |loop| loop == entity.outer_loop }
      faces << {'path' => path, 'pid' => entity.persistent_id, 'entity_id' => entity.entityID,
        'material' => entity.material ? entity.material.name : nil, 'hidden' => entity.hidden?,
        'normal' => entity.normal.to_a, 'rings_inches' => loops.map { |loop| loop.vertices.map { |v| v.position.to_a } },
        'native_area_m2' => entity.area * 0.00064516,
        'ruby_mesh7_area_m2' => ArchControl::Core.face_area_m2(entity, transform),
        'mesh7_points_inches' => mesh.points.map { |p| p.to_a }, 'mesh7_polygons' => mesh.polygons}
    elsif entity.is_a?(Sketchup::Group) || entity.is_a?(Sketchup::ComponentInstance)
      child = entity.is_a?(Sketchup::Group) ? entity.entities : entity.definition.entities
      walk.call(child, transform * entity.transformation, path + [entity.persistent_id])
    end
  end
end
walk.call(model.entities, Geom::Transformation.new, [])
report = {'ok' => true, 'ruby_pid' => Process.pid, 'source_sha256' => Digest::SHA256.file(source).hexdigest,
          'north' => model.shadow_info['NorthAngle'], 'units' => 'inches; areas m2', 'faces' => faces}
File.open(File.join(output,'ruby-face-geometry.json'), 'wb') { |f| f.write(JSON.pretty_generate(report)) }
puts "Native per-face geometry captured: #{faces.length}; source unchanged."
