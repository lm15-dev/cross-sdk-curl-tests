// Dump the HTTP request for a given test case as JSON.
// Uses the canonical lm15 message format.
// Build: cd lm15-go && go build -o ../cross-sdk-curl-tests/output/dump_request_go ../cross-sdk-curl-tests/dump_request.go
package main

import (
	"encoding/json"
	"fmt"
	"os"

	lm15 "github.com/lm15-dev/lm15-go"
	"github.com/lm15-dev/lm15-go/provider"
)

type testCase struct {
	Model       string          `json:"model"`
	Prompt      string          `json:"prompt,omitempty"`
	Messages    []any           `json:"messages,omitempty"`
	System      string          `json:"system,omitempty"`
	Temperature *float64        `json:"temperature,omitempty"`
	MaxTokens   *int            `json:"max_tokens,omitempty"`
	TopP        *float64        `json:"top_p,omitempty"`
	Stop        []string        `json:"stop,omitempty"`
	Stream      bool            `json:"stream,omitempty"`
	Reasoning   map[string]any  `json:"reasoning,omitempty"`
	Tools       []struct {
		Name        string         `json:"name"`
		Description string         `json:"description,omitempty"`
		Parameters  map[string]any `json:"parameters,omitempty"`
	} `json:"tools,omitempty"`
	Provider map[string]any `json:"provider,omitempty"`
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: dump_request <test-case-json>")
		os.Exit(1)
	}

	var tc testCase
	if err := json.Unmarshal([]byte(os.Args[1]), &tc); err != nil {
		fmt.Fprintf(os.Stderr, "invalid JSON: %v\n", err)
		os.Exit(1)
	}

	// Build messages
	var messages []lm15.Message
	if tc.Messages != nil {
		messages = lm15.MessagesFromJSON(tc.Messages)
	} else if tc.Prompt != "" {
		messages = []lm15.Message{lm15.UserMessage(tc.Prompt)}
	}

	// Build tools
	var tools []lm15.Tool
	for _, t := range tc.Tools {
		params := t.Parameters
		if params == nil {
			params = map[string]any{"type": "object", "properties": map[string]any{}}
		}
		tools = append(tools, lm15.Tool{
			Type:        "function",
			Name:        t.Name,
			Description: t.Description,
			Parameters:  params,
		})
	}

	// Build config
	config := lm15.Config{
		MaxTokens:   tc.MaxTokens,
		Temperature: tc.Temperature,
		TopP:        tc.TopP,
		Stop:        tc.Stop,
	}
	if tc.Reasoning != nil {
		config.Reasoning = tc.Reasoning
	}
	if tc.Provider != nil {
		if config.Provider == nil {
			config.Provider = make(map[string]any)
		}
		for k, v := range tc.Provider {
			config.Provider[k] = v
		}
	}

	request := lm15.LMRequest{
		Model:    tc.Model,
		Messages: messages,
		System:   tc.System,
		Tools:    tools,
		Config:   config,
	}

	providerName, err := lm15.ResolveProvider(tc.Model)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	transport := lm15.NewStdTransport(lm15.DefaultPolicy())
	var req lm15.HTTPRequest
	switch providerName {
	case "openai":
		req = provider.NewOpenAI("test-key", transport).BuildRequest(request, tc.Stream)
	case "anthropic":
		req = provider.NewAnthropic("test-key", transport).BuildRequest(request, tc.Stream)
	case "gemini":
		req = provider.NewGemini("test-key", transport).BuildRequest(request, tc.Stream)
	default:
		fmt.Fprintf(os.Stderr, "error: unsupported provider %s\n", providerName)
		os.Exit(1)
	}

	result := lm15.HTTPRequestToDict(req)
	out, _ := json.MarshalIndent(result, "", "  ")
	fmt.Println(string(out))
}
