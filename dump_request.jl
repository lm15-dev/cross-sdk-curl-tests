#!/usr/bin/env julia
# Dump the HTTP request for a given test case as JSON.
# Uses the canonical lm15 message format.

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

kwargs = Dict{Symbol,Any}()
haskey(case, "system") && (kwargs[:system] = case["system"])
haskey(case, "temperature") && (kwargs[:temperature] = Float64(case["temperature"]))
haskey(case, "max_tokens") && (kwargs[:max_tokens] = Int(case["max_tokens"]))
haskey(case, "top_p") && (kwargs[:top_p] = Float64(case["top_p"]))
haskey(case, "stop") && (kwargs[:stop] = convert(Vector{String}, case["stop"]))
haskey(case, "stream") && (kwargs[:stream] = case["stream"])
haskey(case, "reasoning") && (kwargs[:reasoning] = case["reasoning"])

tools_list = LM15.Tool[]
if get(case, "tools", nothing) !== nothing
    for t in case["tools"]
        push!(tools_list, FunctionTool(
            t["name"],
            get(t, "description", nothing);
            parameters=get(t, "parameters", Dict{String,Any}("type" => "object", "properties" => Dict{String,Any}())),
        ))
    end
end
if get(case, "builtin_tools", nothing) !== nothing
    for bt in case["builtin_tools"]
        push!(tools_list, BuiltinTool(bt["name"]; config=get(bt, "builtin_config", nothing)))
    end
end
!isempty(tools_list) && (kwargs[:tools] = tools_list)

# Handle messages (canonical format)
if haskey(case, "messages")
    kwargs[:messages] = messages_from_json(case["messages"])
end

# Provider passthrough
if haskey(case, "provider")
    provider_cfg = get(kwargs, :provider_config, Dict{String,Any}())
    for (k, v) in case["provider"]
        provider_cfg[k] = v
    end
    kwargs[:provider_config] = provider_cfg
end

kwargs[:api_key] = "test-key"

prompt = get(case, "prompt", nothing)
result = dump_http(model, prompt; (; kwargs...)...)
println(LM15.JSON.serialize(result))
