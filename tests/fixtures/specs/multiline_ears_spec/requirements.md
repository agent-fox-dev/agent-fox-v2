# Requirements: Multi-line EARS Spec

## Requirements

### Requirement 1: Feature

#### Acceptance Criteria

1. [99-REQ-1.1] WHEN the user submits input,
   THE system SHALL validate all fields against the schema
   and return a 400 response listing each invalid field.

2. [99-REQ-1.2] WHEN the system receives a batch of records,
   THE system SHALL process all records within 500ms per record.

3. [99-REQ-1.3] The system must do something without EARS keyword.
