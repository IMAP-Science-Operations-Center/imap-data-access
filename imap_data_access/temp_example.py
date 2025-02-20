import processing_input_file
# To construct some dependencies

# In the dependency resolution phase, we collect some information on ancillary files

science_file_1 = processing_input_file.ScienceInput("imap_mag_l1a_norm-magi_20240312_v000.cdf", "imap_mag_l1a_norm-magi_20240310_v000.cdf")
# ancillary_files = processing_input_file.AncillaryInput()
print(science_file_1)

processing_input = processing_input_file.ProcessingInputCollection([science_file_1])

serialized = processing_input.serialize()
print(serialized)
# serialized would get passed to the CLI


# Then, within the CLI, you can deserialize back into a ProcessingInputCollection object
processing_output = processing_input_file.ProcessingInputCollection()
processing_output.deserialize(serialized)

print(processing_output)