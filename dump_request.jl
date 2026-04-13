#!/usr/bin/env julia
# Dump the HTTP request for a given test case as JSON.

using Pkg
Pkg.activate(joinpath(@__DIR__, "..", "lm15-jl"))

pushfirst!(LOAD_PATH, joinpath(@__DIR__, "..", "lm15-jl", "src"))
using LM15

if length(ARGS) < 1
    println(stderr, "usage: dump_request.jl <test-case-json>")
    exit(1)
end

case = LM15.JSON.parse(ARGS[1])
model = case["model"]
prompt = case["prompt"]

kwargs = Dict{Symbol,Any}()
haskey(case, "system") && (kwargs[:system] = case["system"])
haskey(case, "temperature") && (kwargs[:temperature] = Float64(case["temperature"]))
haskey(case, "max_tokens") && (kwargs[:max_tokens] = Int(case["max_tokens"]))
haskey(case, "stream") && (kwargs[:stream] = case["stream"])

if get(case, "tools", nothing) !== nothing
    kwargs[:tools] = [
        FunctionTool(
            t["name"],
            get(t, "description", nothing);
            parameters=get(t, "parameters", Dict{String,Any}("type" => "object", "properties" => Dict{String,Any}())),
        )
        for t in case["tools"]
    ]
end

kwargs[:api_key] = "test-key"
result = dump_http(model, prompt; (; kwargs...)...)
println(LM15.JSON.serialize(result))
