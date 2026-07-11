Feature: AI Studio Website Validation
  As a user
  I want to verify the website components
  So that I ensure the interface is rendered correctly

  Scenario: Verify navigation elements on homepage
    Given the user opens the AI Studio website
    Then there should be exactly 1 element that matches "navigation bar" with identifier "nav"
    And there should be exactly 1 element that matches "main title" with identifier "h1"