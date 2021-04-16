import React from "react"
import PropTypes from "prop-types"
import styled from "styled-components"
import { Link, graphql } from "gatsby"

import GlobalLayout from "../components/layouts/global-layout"
import SEO from "../components/seo"

import {
  Inpage,
  InpageInnerColumns,
  InpageHeader,
  InpageHeadline,
  InpageBody,
  InpageBodyInner,
  InpageTitle,
} from "../styles/inpage"
import Card, { CardHeading, CardList } from "../styles/card"
import media from "../styles/utils/media-queries"

const MethodHeadline = styled(InpageHeadline)`
  ${media.mediumUp`
    grid-column: span 2;
  `}
`

const ActivityCard = styled(Card)`
  > :last-child:not(:first-child) {
    padding-top: 0;
  }
  ${CardHeading} {
    &:after {
      content: "_";
    }
  }
`

function Curriculum({ data }) {
  return (
    <GlobalLayout>
      <SEO title="Activities" />
      <Inpage>
        <InpageHeader>
          <InpageInnerColumns columnLayout="3:1">
            <MethodHeadline>
              <InpageTitle size="jumbo" variation="primary" withDeco>
                Curriculum
              </InpageTitle>
            </MethodHeadline>
          </InpageInnerColumns>
          <InpageInnerColumns columnLayout="2:1">
            <article>
              <p>1. SAFETAG audits serve small scale civil society organizations and independent media houses who have digital security concerns by working with them to identify the risks they face and providing capacity-aware, pragmatic next steps to address them.</p>

              <p>2. Traditional security audits are based upon the assumption that an organization has the time, money, and capacity to aim for perfect security. Low-income at-risk groups have none of these luxuries. SAFETAG combines assessment activities from the the security auditing world with best-practices for working with small scale at-risk organizations.</p>

              <p>3. SAFETAG auditors lead a risk modeling process that helps staff and leadership take an institutional look at their digital security problems, expose vulnerabilities that impact their critical processes and assets, and provide clear reporting and follow up to help the organization strategically move forward and identify the support that they need.
              </p>
            </article>
            </InpageInnerColumns>
            <InpageInnerColumns columnLayout="3:1">
            <MethodHeadline>
              <InpageTitle size="jumbo" variation="primary" withDeco>
                About the Curriculum
              </InpageTitle>
            </MethodHeadline>
          </InpageInnerColumns>
          <InpageInnerColumns columnLayout="2:1">
            <article>
              <p>1. SAFETAG audits serve small scale civil society organizations and independent media houses who have digital security concerns by working with them to identify the risks they face and providing capacity-aware, pragmatic next steps to address them.</p>

              <p>2. Traditional security audits are based upon the assumption that an organization has the time, money, and capacity to aim for perfect security. Low-income at-risk groups have none of these luxuries. SAFETAG combines assessment activities from the the security auditing world with best-practices for working with small scale at-risk organizations.</p>

              <p>3. SAFETAG auditors lead a risk modeling process that helps staff and leadership take an institutional look at their digital security problems, expose vulnerabilities that impact their critical processes and assets, and provide clear reporting and follow up to help the organization strategically move forward and identify the support that they need.
              </p>
            </article>
            </InpageInnerColumns>
        </InpageHeader>
        <InpageBody>
          <InpageBodyInner>
            <CardList>
              {data.allFile.edges.map(
                ({ node }, index) =>
                  node.fields != null &&
                  node.childMarkdownRemark.fields.frontmattermd.summary && (
                    <li key={index}>
                      <ActivityCard
                        variation="secondary"
                        border="primary"
                        as={Link}
                        to={node.fields.slug}
                        withHover
                      >
                        <CardHeading variation="primary">
                          {node.childMarkdownRemark.frontmatter.title}
                        </CardHeading>
                        <p>
                          {
                            node.childMarkdownRemark.fields.frontmattermd
                              .summary.excerpt
                          }
                        </p>
                      </ActivityCard>
                    </li>
                  )
              )}
            </CardList>
          </InpageBodyInner>
        </InpageBody>
      </Inpage>
    </GlobalLayout>
  )
}

Curriculum.propTypes = {
  data: PropTypes.array,
}

export default Curriculum

export const query = graphql`
  query {
    allFile(
      filter: {
        relativeDirectory: { eq: "curriculum" }
        internal: { mediaType: { eq: "text/markdown" } }
      }
    ) {
      edges {
        node {
          fields {
            slug
          }
          childMarkdownRemark {
            frontmatter {
              title
            }
            fields {
              frontmattermd {
                summary {
                  excerpt
                }
              }
            }
          }
        }
      }
    }
  }
`
