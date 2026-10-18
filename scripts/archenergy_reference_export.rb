# encoding: UTF-8
# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
# Read-only validation of the source SKP in a NEW, explicitly owned process.
# Run only via -RubyStartup; original plugin files are loaded, never edited.
require 'json'
require 'digest'

config_path = ENV['ARCHSKETCH_REFERENCE_CONFIG']
if config_path && File.file?(config_path)
  # RubyStartup runs after command-line model processing. A hidden GUI may
  # never dispatch UI timers; export synchronously in this owned process.
  begin
    config = JSON.parse(File.binread(config_path).force_encoding('UTF-8'))
    output = File.expand_path(config.fetch('output'))
    allowed = File.expand_path('../output/archenergy', File.dirname(__FILE__)) + '/'
    unless output.tr('\\', '/').start_with?(allowed.tr('\\', '/'))
      raise 'Reference output must stay inside the ArchSketch evidence folder'
    end
    report = {'status' => 'running', 'ruby_pid' => Process.pid, 'ruby_version' => RUBY_VERSION,
              'startup_mode' => 'synchronous_owned_process'}
    begin
      unless ENV['ARCHSKETCH_REFERENCE_NONCE'] == config.fetch('nonce') &&
             config.fetch('expected_pid').to_i == Process.pid
        raise 'Refused: process ownership does not match the launcher'
      end
      File.open(File.join(output, 'ruby-startup-witness.json'), 'wb') do |f|
        f.write(JSON.pretty_generate(report))
      end
      model = Sketchup.active_model
      source = config.fetch('source')
      # The RP exporter updates material attributes in memory. SketchUp's
      # automatic save may then overwrite an existing AutoSave_<name>.skp.
      # Never open a customer's original path, even for a read-only export.
      unless File.expand_path(source).tr('\\', '/').start_with?(allowed.tr('\\', '/'))
        raise 'Reference source must be an isolated COPY inside the evidence folder'
      end
      clean_untitled = model && model.path.to_s.empty? && !model.modified?
      clean_test_model = model && !model.path.to_s.empty? && !model.modified? &&
        File.expand_path(model.path).tr('\\', '/').downcase == File.expand_path(source).tr('\\', '/').downcase
      unless clean_untitled || clean_test_model
        raise 'Refused: the owned process is not on a clean untitled/test document'
      end
      before = Digest::SHA256.file(source).hexdigest
      report['source_sha256'] = before
      raise 'Wrong source hash' unless before == config.fetch('source_sha256')
      raise 'Could not open the test model' unless clean_test_model || Sketchup.open_file(source)
      model = Sketchup.active_model
      report['sketchup_version'] = Sketchup.version
      report['north_angle'] = model.shadow_info['NorthAngle']
      folder = config.fetch('plugin_folder')
      files = %w[arch_control_config.rb arch_control_renovacni_pas.rb arch_control_core.rb arch_control_export.rb]
      report['source_modules'] = files.map do |name|
        path = File.join(folder, name)
        load path
        {'name' => name, 'sha256' => Digest::SHA256.file(path).hexdigest}
      end
      report['rows'] = ArchControl::Core.collect_rows
      report['zone_table'] = ArchControl::Core.get_zone_report_table
      report['messages'] = []
      methods = [:export_csv, :export_energy_zones_csv, :export_renovacni_pas_csv]
      names = %w[ArchControl_Export.csv ArchControl_Energie_Zony_Export.csv ArchControl_RenovacniPas.csv]
      old_save, old_message = UI.method(:savepanel), UI.method(:messagebox)
      expected = nil
      UI.define_singleton_method(:savepanel) { |*args| expected }
      UI.define_singleton_method(:messagebox) do |*args|
        report['messages'] << args.first.to_s
        IDOK
      end
      begin
        report['exports'] = []
        methods.zip(names).each do |method, name|
          expected = File.join(output, name)
          location = ArchControl::Export.method(method).source_location.first
          raise 'Exporter was not loaded from the requested original source' unless File.expand_path(location) == File.expand_path(File.join(folder, 'arch_control_export.rb'))
          ArchControl::Export.public_send(method)
          raise 'CSV exporter did not create its file' unless File.file?(expected)
          report['exports'] << {'file' => name, 'bytes' => File.size(expected), 'sha256' => Digest::SHA256.file(expected).hexdigest}
        end
      ensure
        UI.define_singleton_method(:savepanel, old_save)
        UI.define_singleton_method(:messagebox, old_message)
      end
      raise 'Source SKP was changed' unless Digest::SHA256.file(source).hexdigest == before
      report['source_unchanged'] = true
      report['status'] = 'complete'
    rescue Exception => error
      report['status'] = 'error'
      report['error'] = "#{error.class}: #{error.message}"
      report['backtrace'] = error.backtrace
    ensure
      # Never save the active test model. The launcher closes only this
      # matching PID after it reads the complete evidence file.
      path = File.join(output, 'ruby-reference-report.json')
      File.open(path + '.tmp', 'wb') { |f| f.write(JSON.pretty_generate(report)) }
      File.rename(path + '.tmp', path)
    end
  end
end
