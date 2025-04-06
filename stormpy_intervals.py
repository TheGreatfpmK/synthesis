import stormpy


model = stormpy.build_interval_model_from_drn("models/test-intervals/ipomdp-tiny-01.drn")

prism = stormpy.parse_prism_program("models/test-intervals/ppomdp-tiny_rewards.nm")
model = stormpy.build_parametric_model(prism)

print(model.transition_matrix)
print(dir(model))